class AssetTypes:
    DOCKER_CONTAINER = "docker_container"
    SYSTEM_RESOURCE = "system_resource"
    HOME_ASSISTANT_ENTITY = "home_assistant_entity"
    UNIFI_DEVICE = "unifi_device"
    ADGUARD_SERVICE = "adguard_service"
    UPS_DEVICE = "ups_device"
    TAILSCALE_NODE = "tailscale_node"
    CALENDAR = "calendar"
    NOTIFICATION_TARGET = "notification_target"


class RelationshipTypes:
    DEPENDS_ON = "depends_on"
    CONTAINS = "contains"
    CONNECTED_TO = "connected_to"
    MANAGED_BY = "managed_by"
    HOSTED_ON = "hosted_on"
