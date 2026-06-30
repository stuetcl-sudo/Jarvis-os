from app.plugins.docker_plugin import DockerPlugin

_plugin = DockerPlugin()


def client():
    return _plugin.client()


def classify(name):
    return _plugin.classify(name)


def list_containers():
    return _plugin.list_containers()
