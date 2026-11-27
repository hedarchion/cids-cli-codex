"""Parse the controls CIDS submits from its server-rendered forms."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from bs4 import BeautifulSoup, Tag


FormValues = Dict[str, Union[str, List[str]]]


def find_form(page: str, form_id: str) -> Optional[Tag]:
    return BeautifulSoup(page, "html.parser").find("form", id=form_id)


def form_values(form: Tag) -> FormValues:
    values: FormValues = {}
    for control in form.select("input[name], select[name], textarea[name]"):
        name = control["name"]
        if not name or control.has_attr("disabled"):
            continue
        if control.find_parent("fieldset", disabled=True):
            continue
        if control.name == "select":
            options = control.find_all("option")
            selected = [option for option in options if option.has_attr("selected")]
            if not control.has_attr("multiple"):
                selected = selected[-1:] or [
                    option for option in options
                    if not option.has_attr("disabled")
                    and not option.find_parent("optgroup", disabled=True)
                ][:1]
            submitted = [
                option.get("value", option.get_text(strip=True)) for option in selected
                if not option.has_attr("disabled")
                and not option.find_parent("optgroup", disabled=True)
            ]
        elif control.name == "textarea":
            submitted = [control.decode_contents(formatter=None)]
        else:
            kind = control.get("type", "text").lower()
            if kind in {"button", "submit", "reset", "file", "image"}:
                continue
            if kind in {"checkbox", "radio"} and not control.has_attr("checked"):
                continue
            submitted = [control.get("value", "on" if kind in {"checkbox", "radio"} else "")]

        for value in submitted:
            previous = values.get(name)
            if isinstance(previous, list):
                previous.append(value)
            elif previous is None:
                values[name] = value
            else:
                values[name] = [previous, value]
    return values
