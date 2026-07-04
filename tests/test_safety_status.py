from app.safety_status import normalize_safety_status, unavailable_status


def payload(entity_id, state, name=None):
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": {"friendly_name": name or entity_id},
    }


def settings():
    return {
        "doors": ["binary_sensor.back_door"],
        "motion": ["binary_sensor.hall_motion"],
        "cameras": ["camera.driveway", "camera.garden"],
    }


def test_all_clear():
    result = normalize_safety_status(
        settings(),
        {
            "binary_sensor.back_door": payload("binary_sensor.back_door", "off", "Bagdør"),
            "binary_sensor.hall_motion": payload("binary_sensor.hall_motion", "off", "Gang"),
            "camera.driveway": payload("camera.driveway", "idle", "Indkørsel"),
            "camera.garden": payload("camera.garden", "streaming", "Have"),
        },
    )
    assert result["internet"] == {"status": "ok", "label": "Online"}
    assert result["doors"] == {"status": "ok", "label": "Lukket"}
    assert result["motion"] == {"status": "ok", "label": "Roligt"}
    assert result["cameras"] == {"status": "ok", "label": "OK"}


def test_open_door_motion_and_camera_problem_are_plain_language():
    result = normalize_safety_status(
        settings(),
        {
            "binary_sensor.back_door": payload("binary_sensor.back_door", "on", "Bagdør"),
            "binary_sensor.hall_motion": payload("binary_sensor.hall_motion", "on", "Gang"),
            "camera.driveway": payload("camera.driveway", "unavailable", "Indkørsel"),
            "camera.garden": payload("camera.garden", "idle", "Have"),
        },
    )
    assert result["doors"] == {"status": "warning", "label": "Bagdør åben"}
    assert result["motion"] == {"status": "warning", "label": "Bevægelse"}
    assert result["cameras"] == {"status": "warning", "label": "1 offline"}


def test_unconfigured_categories_are_unknown_not_errors():
    result = normalize_safety_status({"doors": [], "motion": [], "cameras": []}, {})
    assert result["doors"] == {"status": "unknown", "label": "Ikke valgt"}
    assert result["motion"] == {"status": "unknown", "label": "Ikke valgt"}
    assert result["cameras"] == {"status": "unknown", "label": "Ikke valgt"}


def test_unavailable_status_keeps_family_safe_shape():
    result = unavailable_status("Home Assistant svarer ikke")
    assert set(result) == {"status", "internet", "doors", "motion", "cameras"}
    assert result["internet"] == {"status": "ok", "label": "Online"}
    assert result["doors"] == {"status": "unknown", "label": "Home Assistant svarer ikke"}


def test():
    test_all_clear()
    test_open_door_motion_and_camera_problem_are_plain_language()
    test_unconfigured_categories_are_unknown_not_errors()
    test_unavailable_status_keeps_family_safe_shape()
    print("Safety status tests OK")


if __name__ == "__main__":
    test()
