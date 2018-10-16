#!/bin/env python
# -*- coding:utf-8 -*-
from __future__ import print_function

import datetime
import logging
import os
import pprint
import re
import sys
import six
import shutil
import time
import tempfile
import jinja2
from oslo_config import cfg
from lobuilder import exception
from lobuilder.common import config as common_config
from lobuilder.template import filters as jinja_filters
from lobuilder.template import methods as jinja_methods


def make_a_logger(conf=None, image_name=None):
    if image_name:
        log = logging.getLogger(".".join([__name__, image_name]))
    else:
        log = logging.getLogger(__name__)
    if not log.handlers:
        if conf is None or not conf.logs_dir or not image_name:
            handler = logging.StreamHandler(sys.stdout)
            log.propagate = False
        else:
            filename = os.path.join(conf.logs_dir, "%s.log" % image_name)
            handler = logging.FileHandler(filename, delay=True)
        handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
        log.addHandler(handler)
    if conf is not None and conf.debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)
    return log


LOG = make_a_logger()

# Image status constants.
STATUS_CONNECTION_ERROR = 'connection_error'
STATUS_PUSH_ERROR = 'push_error'
STATUS_ERROR = 'error'
STATUS_PARENT_ERROR = 'parent_error'
STATUS_BUILT = 'built'
STATUS_BUILDING = 'building'
STATUS_UNMATCHED = 'unmatched'
STATUS_MATCHED = 'matched'
STATUS_UNPROCESSED = 'unprocessed'


class Image(object):
    def __init__(self, name, canonical_name, path, parent_name='',
                 status=STATUS_UNPROCESSED, parent=None,
                 source=None, logger=None):
        self.name = name
        self.canonical_name = canonical_name
        self.path = path
        self.status = status
        self.parent = parent
        self.source = source
        self.parent_name = parent_name
        if logger is None:
            logger = make_a_logger(image_name=name)
        self.logger = logger
        self.children = []
        self.plugins = []

    def copy(self):
        c = Image(self.name, self.canonical_name, self.path,
                  logger=self.logger, parent_name=self.parent_name,
                  status=self.status, parent=self.parent)
        if self.source:
            c.source = self.source.copy()
        if self.children:
            c.children = list(self.children)
        if self.plugins:
            c.plugins = list(self.plugins)
        return c

    def __repr__(self):
        return ("Image(%s, %s, %s, parent_name=%s,"
                " status=%s, parent=%s, source=%s)") % (
                   self.name, self.canonical_name, self.path,
                   self.parent_name, self.status, self.parent, self.source)


class Worker(object):
    def __init__(self, conf):
        self.conf = conf
        self.images_dir = self._get_images_dir()

        self.registry = conf.registry
        if self.registry:
            self.namespace = self.registry + '/' + conf.namespace
        else:
            self.namespace = conf.namespace

        self.base = conf.base
        self.base_tag = conf.base_tag
        self.install_type = conf.install_type
        self.tag = conf.tag
        self.images = list()
        rpm_setup_config = ([repo_file for repo_file in
                             conf.rpm_setup_config if repo_file is not None])
        self.rpm_setup = self.build_rpm_setup(rpm_setup_config)

        self._check_base_distribute()
        self._check_install_type()

        self.image_prefix = self.base + '-' + self.install_type + '-'

        self.regex = conf.regex
        self.image_statuses_bad = dict()
        self.image_statuses_good = dict()
        self.image_statuses_unmatched = dict()
        self.maintainer = conf.maintainer

    def _get_images_dir(self):
        possible_paths = (
            PROJECT_ROOT,
            os.path.join(sys.prefix, 'share/kolla'),
            os.path.join(sys.prefix, 'local/share/kolla'))

        for path in possible_paths:
            image_path = os.path.join(path, 'docker')
            # NOTE(SamYaple): We explicty check for the base folder to ensure
            #                 this is the correct path
            # TODO(SamYaple): Improve this to make this safer
            if os.path.exists(os.path.join(image_path, 'base')):
                LOG.info('Found the docker image folder at %s', image_path)
                return image_path
        else:
            raise exception.DirNotFoundException('Image dir can not '
                                                 'be found')

    def _check_base_distribute(self):
        rh_base = ['centos', 'oraclelinux', 'rhel']
        rh_type = ['source', 'binary', 'rdo', 'rhos']
        deb_base = ['ubuntu', 'debian']
        deb_type = ['source', 'binary']
        if not ((self.base in rh_base and self.install_type in rh_type) or
                    (self.base in deb_base and self.install_type in deb_type)):
            raise exception.MismatchBaseTypeException(
                '{} is unavailable for {}'.format(self.install_type, self.base)
            )

    def _check_install_type(self):
        if self.install_type == 'binary':
            self.install_metatype = 'rdo'
        elif self.install_type == 'source':
            self.install_metatype = 'mixed'
        elif self.install_type == 'rdo':
            self.install_type = 'binary'
            self.install_metatype = 'rdo'
        elif self.install_type == 'rhos':
            self.install_type = 'binary'
            self.install_metatype = 'rhos'
        else:
            raise exception.UnknownBuildTypeException(
                'Unknown install type'
            )

    def build_rpm_setup(self, rpm_setup_config):
        """Generates a list of docker commands based on provided configuration.

        :param rpm_setup_config: A list of .rpm or .repo paths or URLs
        :return: A list of docker commands
        """
        rpm_setup = list()
        for config in rpm_setup_config:
            if config.endswith('.rpm'):
                # RPM files can be installed with yum from file path or url
                cmd = "RUN yum -y install {}".format(config)
            elif config.endswith('.repo'):
                if config.startswith('http'):
                    # Curl http://url/etc.repo to /etc/yum.repos.d/etc.repo
                    name = config.split('/')[-1]
                    cmd = "RUN curl -L {} -o /etc/yum.repos.d/{}".format(
                        config, name)
                else:
                    # Copy .repo file from filesystem
                    cmd = "COPY {} /etc/yum.repos.d/".format(config)
            else:
                raise exception.RpmSetupUnknownConfig(
                    'RPM setup must be provided as .rpm or .repo files.'
                    ' Attempted configuration was {}'.format(config)
                )
            rpm_setup.append(cmd)
        return rpm_setup

    def copy_apt_files(self):
        if self.conf.apt_sources_list:
            shutil.copyfile(
                self.conf.apt_sources_list,
                os.path.join(self.working_dir, "base", "sources.list")
            )

        if self.conf.apt_preferences:
            shutil.copyfile(
                self.conf.apt_preferences,
                os.path.join(self.working_dir, "base", "apt_preferences")
            )

    def extend_docker_path(self, working_dir):
        edp = self.conf.extend_docker_path
        if edp and os.path.exists(edp):
            for name in os.listdir(edp):
                src_dir = os.path.join(edp, name)
                image_dir = os.path.join(working_dir, name)
                if os.path.isdir(src_dir):
                    if os.path.exists(image_dir):
                        shutil.rmtree(image_dir)
                    shutil.copytree(os.path.join(edp, name), image_dir)

    def setup_working_dir(self):
        """Creates a working directory for use while building"""
        ts = time.time()
        ts = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d_%H-%M-%S_')
        self.temp_dir = tempfile.mkdtemp(prefix='lobuilder-' + ts)
        self.working_dir = os.path.join(self.temp_dir, 'docker')
        shutil.copytree(self.images_dir, self.working_dir)
        self.extend_docker_path(self.working_dir)
        self.copy_apt_files()
        LOG.debug('Created working dir: %s', self.working_dir)

    def find_dockerfiles(self):
        """Recursive search for Dockerfiles in the working directory"""
        self.docker_build_paths = list()
        path = self.working_dir
        filename = 'Dockerfile.j2'
        for root, dirs, names in os.walk(path):
            if filename in names:
                self.docker_build_paths.append(root)
                LOG.debug('Found %s', root.split(self.working_dir)[1])
        LOG.debug('Found %d Dockerfiles', len(self.docker_build_paths))

    def get_users(self):
        all_sections = (set(six.iterkeys(self.conf._groups)) |
                        set(self.conf.list_all_sections()))
        ret = dict()
        for section in all_sections:
            match = re.search('^.*-user$', section)
            if match:
                user = self.conf[match.group(0)]
                ret[match.group(0)[:-5]] = {
                    'uid': user.uid,
                    'gid': user.gid,
                }
        return ret

    def _get_filters(self):
        filters = {
            'customizable': jinja_filters.customizable,
        }
        return filters

    def _get_methods(self):
        """Mapping of available Jinja methods

        return a dictionary that maps available function names and their
        corresponding python methods to make them available in jinja templates
        """

        return {
            'debian_package_install': jinja_methods.debian_package_install,
        }

    def _merge_overrides(self, overrides):
        tpl_name = os.path.basename(overrides[0])
        with open(overrides[0], 'r') as f:
            tpl_content = f.read()
        for override in overrides[1:]:
            with open(override, 'r') as f:
                cont = f.read()
            # Remove extends header
            cont = re.sub(r'.*\{\%.*extends.*\n', '', cont)
            tpl_content += cont
        return {tpl_name: tpl_content}

    def create_dockerfiles(self):
        kolla_version = common_config.KOLLA_VERSION
        supported_distro_release = common_config.DISTRO_RELEASE.get(
            self.base)
        for path in self.docker_build_paths:
            template_name = "Dockerfile.j2"
            image_name = path.split("/")[-1]
            values = {'base_distro': self.base,
                      'base_image': self.conf.base_image,
                      'base_distro_tag': self.base_tag,
                      'supported_distro_release': supported_distro_release,
                      'install_metatype': self.install_metatype,
                      'image_prefix': self.image_prefix,
                      'install_type': self.install_type,
                      'namespace': self.namespace,
                      'tag': self.tag,
                      'maintainer': self.maintainer,
                      'kolla_version': kolla_version,
                      'image_name': image_name,
                      'users': self.get_users(),
                      'rpm_setup': self.rpm_setup}
            env = jinja2.Environment(  # nosec: not used to render HTML
                loader=jinja2.FileSystemLoader(self.working_dir))
            env.filters.update(self._get_filters())
            env.globals.update(self._get_methods())
            tpl_path = os.path.join(
                os.path.relpath(path, self.working_dir),
                template_name)
            template = env.get_template(tpl_path)
            if self.conf.template_override:
                tpl_dict = self._merge_overrides(self.conf.template_override)
                template_name = os.path.basename(tpl_dict.keys()[0])
                values['parent_template'] = template
                env = jinja2.Environment(  # nosec: not used to render HTML
                    loader=jinja2.DictLoader(tpl_dict))
                env.filters.update(self._get_filters())
                env.globals.update(self._get_methods())
                template = env.get_template(template_name)
            content = template.render(values)
            content_path = os.path.join(path, 'Dockerfile')
            with open(content_path, 'w') as f:
                LOG.debug("Rendered %s into:", tpl_path)
                LOG.debug(content)
                f.write(content)
                LOG.debug("Wrote it to %s", content_path)

    def set_time(self):
        for root, dirs, files in os.walk(self.working_dir):
            for file_ in files:
                os.utime(os.path.join(root, file_), (0, 0))
            for dir_ in dirs:
                os.utime(os.path.join(root, dir_), (0, 0))
        LOG.debug('Set atime and mtime to 0 for all content in working dir')

    def build_image_list(self):
        def process_source_installation(image, section):
            installation = dict()
            # NOTE(jeffrey4l): source is not needed when the type is None
            if self.conf._get('type', self.conf._get_group(section)) is None:
                if image.parent_name is None:
                    LOG.debug('No source location found in section %s',
                              section)
            else:
                installation['type'] = self.conf[section]['type']
                installation['source'] = self.conf[section]['location']
                installation['name'] = section
                if installation['type'] == 'git':
                    installation['reference'] = self.conf[section]['reference']
            return installation

        all_sections = (set(six.iterkeys(self.conf._groups)) |
                        set(self.conf.list_all_sections()))
        for path in self.docker_build_paths:
            # Reading parent image name
            with open(os.path.join(path, 'Dockerfile')) as f:
                content = f.read()

            image_name = os.path.basename(path)
            canonical_name = (self.namespace + '/' + self.image_prefix +
                              image_name + ':' + self.tag)
            parent_search_pattern = re.compile(r'^FROM.*$', re.MULTILINE)
            match = re.search(parent_search_pattern, content)
            if match:
                parent_name = match.group(0).split(' ')[1]
            else:
                parent_name = ''
            del match
            image = Image(image_name, canonical_name, path,
                          parent_name=parent_name,
                          logger=make_a_logger(self.conf, image_name))

            if self.install_type == 'source':
                # NOTE(jeffrey4l): register the opts if the section didn't
                # register in the kolla/common/config.py file
                if image.name not in self.conf._groups:
                    self.conf.register_opts(common_config.get_source_opts(),
                                            image.name)
                image.source = process_source_installation(image, image.name)
                for plugin in [match.group(0) for match in
                               (re.search('^{}-plugin-.+'.format(image.name),
                                          section) for section in
                                all_sections) if match]:
                    try:
                        self.conf.register_opts(
                            common_config.get_source_opts(),
                            plugin
                        )
                    except cfg.DuplicateOptError:
                        LOG.debug('Plugin %s already registered in config',
                                  plugin)
                    image.plugins.append(
                        process_source_installation(image, plugin))
            self.images.append(image)

    def find_parents(self):
        """Associate all images with parents and children"""
        sort_images = dict()

        for image in self.images:
            sort_images[image.canonical_name] = image

        for parent_name, parent in sort_images.items():
            for image in sort_images.values():
                if image.parent_name == parent_name:
                    parent.children.append(image)
                    image.parent = parent

    def filter_images(self):
        """Filter which images to build"""
        filter_ = list()

        if self.regex:
            filter_ += self.regex
        elif self.conf.profile:
            for profile in self.conf.profile:
                if profile not in self.conf.profiles:
                    self.conf.register_opt(cfg.ListOpt(profile,
                                                       default=[]),
                                           'profiles')
                if len(self.conf.profiles[profile]) == 0:
                    msg = 'Profile: {} does not exist'.format(profile)
                    raise ValueError(msg)
                else:
                    filter_ += self.conf.profiles[profile]

        if filter_:
            patterns = re.compile(r"|".join(filter_).join('()'))
            for image in self.images:
                if image.status == STATUS_MATCHED:
                    continue
                if re.search(patterns, image.name):
                    image.status = STATUS_MATCHED
                    while (image.parent is not None and
                                   image.parent.status != STATUS_MATCHED):
                        image = image.parent
                        image.status = STATUS_MATCHED
                        LOG.debug('Image %s matched regex', image.name)
                else:
                    image.status = STATUS_UNMATCHED
        else:
            for image in self.images:
                image.status = STATUS_MATCHED

    def save_dependency(self, to_file):
        try:
            import graphviz
        except ImportError:
            LOG.error('"graphviz" is required for save dependency')
            raise
        dot = graphviz.Digraph(comment='Docker Images Dependency')
        dot.body.extend(['rankdir=LR'])
        for image in self.images:
            if image.status not in [STATUS_MATCHED]:
                continue
            dot.node(image.name)
            if image.parent is not None:
                dot.edge(image.parent.name, image.name)

        with open(to_file, 'w') as f:
            f.write(dot.source)

    def list_images(self):
        for count, image in enumerate([image for image in self.images if
                                       image.status == STATUS_MATCHED]):
            print(count + 1, ':', image.name)

    def list_dependencies(self):
        match = False
        for image in self.images:
            if image.status in [STATUS_MATCHED]:
                match = True
            if image.parent is None:
                base = image

        if not match:
            print('Nothing matched!')
            return

        def list_children(images, ancestry):
            children = six.next(iter(ancestry.values()))
            for image in images:
                if image.status not in [STATUS_MATCHED]:
                    continue
                if not image.children:
                    children.append(image.name)
                else:
                    newparent = {image.name: []}
                    children.append(newparent)
                    list_children(image.children, newparent)

        ancestry = {base.name: []}
        list_children(base.children, ancestry)
        pprint.pprint(ancestry)


def run_build():
    """Build container images.

    :return: A 3-tuple containing bad, good, and unmatched container image
    status dicts, or None if no images were built.
    """
    conf = cfg.ConfigOpts()
    common_config.parse(conf, sys.argv[1:], prog='lobuilder')

    if conf.debug:
        LOG.setLevel(logging.DEBUG)

    wk = Worker(conf)
    wk.setup_working_dir()
    wk.find_dockerfiles()
    wk.create_dockerfiles()

    if conf.template_only:
        LOG.info('Dockerfiles are generated in %s', wk.working_dir)
        return
    # We set the atime and mtime to 0 epoch to preserve allow the Docker cache
    # to work like we want. A different size or hash will still force a rebuild
    wk.set_time()

    if conf.save_dependency:
        wk.build_image_list()
        wk.find_parents()
        wk.filter_images()
        wk.save_dependency(conf.save_dependency)
        LOG.info('Docker images dependency are saved in %s',
                 conf.save_dependency)
        return
    if conf.list_images:
        wk.build_image_list()
        wk.find_parents()
        wk.filter_images()
        wk.list_images()
        return
    if conf.list_dependencies:
        wk.build_image_list()
        wk.find_parents()
        wk.filter_images()
        wk.list_dependencies()
        return
