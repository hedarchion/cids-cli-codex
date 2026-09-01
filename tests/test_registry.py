from cids_cli.registry import FUNCTIONS, REGISTRY, get_function


def test_registry_names_are_unique_and_paths_are_scoped():
    names = [spec.name for spec in FUNCTIONS]
    assert len(names) == len(set(names))
    assert len(names) >= 80
    for spec in FUNCTIONS:
        assert spec.method in {"GET", "POST"}
        assert not spec.path.startswith("/")
        assert "://" not in spec.path


def test_critical_browser_observed_routes_are_exact():
    assert get_function("home").path == "main.php"
    assert get_function("dashboard.detail").path.startswith("dashboard.php?action=detail")
    assert get_function("profile.save").path == "admin9.php"
    assert get_function("reference.copy").path.startswith("record.php?action=copymiw")
    assert get_function("yip.delete").path.startswith("record.php?action=delete_rpt")
    assert get_function("smart-search").json_body is True


def test_all_side_effecting_legacy_gets_are_guarded():
    names = ("reference.copy", "yip.copy", "yip.delete", "yip.share", "cocurricular.students-assign")
    for name in names:
        spec = get_function(name)
        assert spec.method == "GET"
        assert spec.mutating is True


def test_aliases_resolve_to_the_same_spec():
    assert REGISTRY["open-miw"] is REGISTRY["miw.open"]
    assert REGISTRY["open-rph"] is REGISTRY["lesson.open"]
