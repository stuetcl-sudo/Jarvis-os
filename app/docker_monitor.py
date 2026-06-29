from app.plugins.docker_plugin import DockerPlugin

_plugin = DockerPlugin()


def client():
    return _plugin.client()


def classify(name):
    return _plugin.classify(name)


def list_containers():
    return _plugin.list_containers()


def start_container(name):
    return _plugin.start_container(name)


restart_container = start_container
