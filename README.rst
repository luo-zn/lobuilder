==================
Lobuilder Overview
==================

此项目基于OpenStack的Kolla项目进行扩展，用于构建docker镜像。原本的Kolla主要针对
Openstack相关项目进行docker镜像构建。扩展以后，通过在配置文件添加自定义的路径
(如extend_docker_path=/home/custom-docker-files-dir)，便可以将自定义的dockerfile
进行容器构建。

===========
Quick Start
===========

进入项目，执行以下命令生成conf文件
