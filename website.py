import datetime
import logging
from typing import Type

import tomlkit
import tomlkit.exceptions

import breadcord.config
from . import bot
from quart import Quart, render_template, request, redirect

app = Quart(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
logger = logging.getLogger(__name__)


def map_python_types_to_html(
    python_type: Type[
        int | float | str | datetime.datetime | datetime.date | datetime.time | bool
    ],
) -> str:
    """
    A utility function to convert from Python setting types to HTML input types.
    An exception is made for float, which is <input type="number" step="any"> and
    Jinja needs to have a way to distinguish between ints and floats.

    :param python_type: Python type of the setting
    :return: HTML input type, except for float
    """
    python_to_html_types = {
        int: "number",
        float: "float",
        str: "text",
        datetime.datetime: "datetime-local",
        datetime.date: "date",
        datetime.time: "time",
        bool: "checkbox",
    }
    return python_to_html_types.get(python_type, "text")


def convert_python_value_to_html(
    python_value: int
    | float
    | bool
    | str
    | datetime.datetime
    | datetime.date
    | datetime.time,
) -> str | bool:
    """
    A utility function for converting Python setting values to HTML input values.
    Currently, the function just removes the timezone information from datetime and time
    objects, as HTML input elements do not support timezones. It also doesn't modify strings
    or booleans.

    :param python_value: Python value of the setting
    :return: HTML input value
    """
    if isinstance(python_value, datetime.datetime) or isinstance(
        python_value, datetime.time
    ):
        python_value = python_value.replace(tzinfo=None)

    if isinstance(python_value, str) or isinstance(python_value, bool):
        return python_value

    return tomlkit.item(python_value).as_string()


@app.get("/settings")
async def settings_get():
    module_ids = bot.settings.get("modules").value
    if not isinstance(module_ids, list):
        raise ValueError("Modules is not list")

    module_settings = [
        {
            "id": "general",
            "name": "General",
            "description": "General settings for Breadcord",
            "settings": [
                {
                    "id": setting.path_id(),
                    "type": map_python_types_to_html(setting.type),
                    "value": convert_python_value_to_html(setting.value),
                }
                for setting in bot.settings
            ],
        }
    ]

    for group in bot.settings.children():
        if group.key not in module_ids:
            logger.info(
                "Found a top-level SettingsGroup that isn't a module, adding it as a general setting. obj: %s",
                group,
            )
            module_settings[0]["settings"].extend(
                [
                    {
                        "id": s.path_id(),
                        "type": map_python_types_to_html(s.type),
                        "value": convert_python_value_to_html(s.value),
                    }
                    for s in group.walk(skip_groups=True)
                    if isinstance(s, breadcord.config.Setting)
                ]
            )
        else:
            module_settings.append(
                {
                    "id": group.key,
                    "name": bot.modules.get(group.key).manifest.name,
                    "description": bot.modules.get(group.key).manifest.description,
                    "settings": [
                        {
                            "id": s.path_id(),
                            "type": map_python_types_to_html(s.type),
                            "value": convert_python_value_to_html(s.value),
                        }
                        for s in group.walk(skip_groups=True)
                        if isinstance(s, breadcord.config.Setting)
                    ],
                }
            )

    return await render_template("settings.html", settings=module_settings)


# technically this should be a PUT request, but I'm not adding Javascript just for that.
@app.post("/settings")
async def submit_settings():
    new_settings = await request.form
    logger.debug("Settings submitted with values: %s", new_settings)

    for setting in bot.settings.walk(skip_groups=True):
        if not isinstance(setting, breadcord.config.Setting):
            logger.error(
                "Did not get setting by walking and skipping setting groups! Got %s",
                setting,
            )
            continue

        new_values = new_settings.getlist(setting.path_id())
        if len(new_values) == 0:
            # This wasn't submitted
            logging.warning(
                "Setting was not submitted through form: %s", setting.path_id()
            )
            continue

        # Get the last value of the key specified by the form
        # this accounts for checkboxes/booleans where a hidden input is used to submit a value when the checkbox is not
        # checked.
        new_value = new_values[-1]

        if setting.type is int:
            setting.value = int(new_value)
        elif setting.type is float:
            setting.value = float(new_value)
        elif setting.type is bool:
            setting.value = new_value == "true"
        elif setting.type is datetime.datetime:
            setting.value = datetime.datetime.fromisoformat(new_value)
        elif setting.type is datetime.date:
            setting.value = datetime.date.fromisoformat(new_value)
        elif setting.type is datetime.time:
            setting.value = datetime.time.fromisoformat(new_value)

    return redirect("/dashboard")
