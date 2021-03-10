import os
import ast
import re
import yaml
from jinja2 import Environment, BaseLoader, FileSystemLoader, select_autoescape
import traceback
import functools
import time
import cProfile
import io
import pstats
import datetime
from collections import OrderedDict

import appdaemon.utils as ha


class Dashboard:
    def __init__(self, config_dir, logging, **kwargs):
        #
        # Set Defaults
        #
        self.dash_install_dir = os.path.dirname(__file__)
        self.config_dir = config_dir
        self.logging = logging
        self.logger = logging.get_child("_dashboard")
        self.access = logging.get_access()
        self.dashboard_dir = os.path.join(config_dir, "dashboards")
        self.profile_dashboard = False
        self.compile_dir = os.path.join(self.config_dir, "compiled")
        self.javascript_dir = None
        self.compiled_javascript_dir = os.path.join(self.compile_dir, "javascript")
        self.compiled_html_dir = os.path.join(self.compile_dir, "html")
        self.template_dir = None
        self.css_dir = None
        self.compiled_css_dir = os.path.join(self.compile_dir, "css")
        self.fonts_dir = None
        self.webfonts_dir = None
        self.images_dir = None
        self.base_url = ""
        self.dash_force_compile = False
        self.dash_compile_on_start = False
        self.max_include_depth = 10
        self.fa4compatibility = False
        self.transport = "ws"
        self.title = "HADashboard"
        #
        # Process any overrides
        #
        self._process_arg("profile_dashboard", kwargs)
        self._process_arg("dashboard_dir", kwargs)
        self._process_arg("compile_dir", kwargs)
        self._process_arg("javascript_dir", kwargs)
        self._process_arg("compiled_javascript_dir", kwargs)
        self._process_arg("compiled_html_dir", kwargs)
        self._process_arg("template_dir", kwargs)
        self._process_arg("css_dir", kwargs)
        self._process_arg("compiled_css_dir", kwargs)
        self._process_arg("fonts_dir", kwargs)
        self._process_arg("webfonts_dir", kwargs)
        self._process_arg("images_dir", kwargs)
        self._process_arg("base_url", kwargs)
        self._process_arg("dash_force_compile", kwargs)
        self._process_arg("dash_compile_on_start", kwargs)
        self._process_arg("max_include_depth", kwargs)
        self._process_arg("fa4compatibility", kwargs)
        self._process_arg("transport", kwargs)
        self._process_arg("title", kwargs)
        #
        # Create some dirs
        #
        try:
            js = os.path.join(self.compile_dir, "javascript")
            css = os.path.join(self.compile_dir, "css")
            if not os.path.isdir(self.compile_dir):
                os.makedirs(self.compile_dir)

            if not os.path.isdir(os.path.join(self.compile_dir, "javascript")):
                os.makedirs(js)

            if not os.path.isdir(os.path.join(self.compile_dir, "css")):
                os.makedirs(css)

            ha.check_path("css", self.logger, css, permissions="rwx")
            ha.check_path("javascript", self.logger, js, permissions="rwx")

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during HADashboard initialization")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)

        #
        # Set a start time
        #
        self.start_time = datetime.datetime.now()

    def _timeit(func):
        @functools.wraps(func)
        def newfunc(self, *args, **kwargs):
            start_time = time.time()
            result = func(self, *args, **kwargs)
            elapsed_time = time.time() - start_time
            self.access.info("function [%s] finished in %s ms", func.__name__, int(elapsed_time * 1000))
            return result

        return newfunc

    def _profile_this(fn):
        def profiled_fn(self, *args, **kwargs):
            pr = None
            if self.profile_dashboard:
                pr = cProfile.Profile()
                pr.enable()

            dash = fn(self, *args, **kwargs)

            if self.profile_dashboard:
                pr.disable()
                s = io.StringIO()
                sortby = "cumulative"
                ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
                ps.print_stats()
                print(s.getvalue())
            return dash

        return profiled_fn

    def _process_arg(self, arg, kwargs):
        if kwargs:
            if arg in kwargs:
                setattr(self, arg, kwargs[arg])

    # noinspection PyUnresolvedReferences,PyUnresolvedReferences,PyUnresolvedReferences,PyUnresolvedReferences
    def _load_css_params(self, skin, skindir):
        yaml_path = os.path.join(skindir, "variables.yaml")
        if os.path.isfile(yaml_path):
            with open(yaml_path, "r") as yamlfd:
                css_text = yamlfd.read()
            try:
                css = self._load_yaml(css_text)
            except yaml.YAMLError as exc:
                self.logger.warning("Error loading CSS variables")
                self._log_yaml_error(exc)
                return None
            if css is None:
                return {}
            else:
                return self._resolve_css_params(css, css)
        else:
            self.logger.warning("Error loading variables.yaml for skin '%s'", skin)
            return None

    def _resolve_css_params(self, fields, subs):
        done = False
        variable = re.compile("\\$(\\w+)")
        index = 0
        while not done and index < 100:
            index += 1
            done = True
            for varline in fields:
                if isinstance(fields[varline], dict):
                    fields[varline] = self._resolve_css_params(fields[varline], subs)
                elif fields[varline] is not None and type(fields[varline]) == str:
                    _vars = variable.finditer(fields[varline])
                    for var in _vars:
                        subvar = var.group()[1:]
                        if subvar in subs:
                            done = False
                            fields[varline] = fields[varline].replace(var.group(), subs[subvar], 1)
                        else:
                            self.logger.warning("Variable definition not found in CSS Skin variables: $%s", subvar)
                            fields[varline] = ""

        if index == 100:
            self.logger.warning("Unable to resolve CSS Skin variables, check for circular references")

        return fields

    @staticmethod
    def _get_styles(style_str, name, field):
        #
        # Parse styles in order from a string and allow later entries to override earlier ones
        #
        result = {}
        styles = style_str.split(";")
        for style in styles:
            if style != "" and style is not None:
                pieces = style.split(":", 1)
                result[pieces[0].strip()] = pieces[1]

        return result

    def _merge_styles(self, widget, name):
        result = {}
        for key in widget:
            if key == "css" or key == "static_css":
                result[key] = self._merge_styles(widget[key], name)
            elif key.find("style") == -1:
                result[key] = widget[key]
            else:
                line = ""
                styles = self._get_styles(widget[key], name, key)
                for style in styles:
                    line = line + style + ":" + styles[style] + ";"
                result[key] = line
        return result

    def _do_subs(self, value, _vars):
        if isinstance(value, dict):
            result = {}
            templates = {}
            for (key, value) in value.items():
                processed, t = self._do_subs(value, _vars)
                result[key] = processed
                templates = {**templates, **t}
            return result, templates
        elif isinstance(value, list):
            result = []
            templates = {}
            for item in value:
                processed, t = self._do_subs(item)
                result.append(processed)
                templates = {**templates, **t}
            return result, templates
        elif isinstance(value, str):
            templates = {}
            for ikey in _vars:
                match = "{{{{{}}}}}".format(ikey)
                if match in value:
                    templates[ikey] = 1
                    value = value.replace(match, _vars[ikey])

            # Replace variables that are still left with an empty string.
            value = re.sub("{{(.+)}}", "", value)
            return value, templates
        else:
            return value, {}

    # noinspection PyUnresolvedReferences
    def _load_widget(self, dash, includes, name, css_vars, global_parameters):  # noqa C901
        instantiated_widget = None
        #
        # Check if we have already encountered a definition
        #
        for include in includes:
            if name in include:
                instantiated_widget = include[name]
        #
        # If not, go find it elsewhere
        #
        if instantiated_widget is None:
            # Try to find in in a yaml file
            yaml_path = os.path.join(self.dashboard_dir, "{}.yaml".format(name))
            if os.path.isfile(yaml_path):
                with open(yaml_path, "r") as yamlfd:
                    widget = yamlfd.read()
                try:
                    instantiated_widget = self._load_yaml(widget)
                except yaml.YAMLError as exc:
                    self._log_error(dash, name, "Error while parsing dashboard '{}':".format(yaml_path))
                    self._log_yaml_dash_error(dash, name, exc)
                    return self.error_widget("Error loading widget")

            elif name.find(".") != -1:
                #
                # No file, check if it is implicitly defined via an entity id
                #
                parts = name.split(".")
                instantiated_widget = {"widget_type": parts[0], "entity": name, "title_is_friendly_name": 1}
            else:
                self.logger.warning("Unable to find widget definition for '%s'", name)
                # Return some valid data so the browser will render a blank widget
                return self.error_widget("Widget definition not found")

        widget_type = None
        try:
            if "widget_type" not in instantiated_widget:
                return self.error_widget("Widget type not specified")

            #
            # One way or another we now have the widget definition
            #
            widget_type = instantiated_widget["widget_type"]

            if widget_type == "text_sensor":
                self.logger.warning(
                    "'text_sensor' widget is deprecated, please use 'sensor' instead for widget '%s'", name
                )

            # Check for custom base widgets first
            if os.path.isdir(os.path.join(self.config_dir, "custom_widgets", widget_type)):
                # This is a custom base widget so return it in full
                return self._resolve_css_params(instantiated_widget, css_vars)

            # Now regular base widgets
            if os.path.isdir(os.path.join(self.dash_install_dir, "widgets", widget_type)):
                # This is a base widget so return it in full
                return self._resolve_css_params(instantiated_widget, css_vars)

            # We are working with a derived widget so we need to do some merges and substitutions

            # first check for custom widget

            yaml_path = os.path.join(self.config_dir, "custom_widgets", "{}.yaml".format(widget_type))
            if not os.path.isfile(yaml_path):
                yaml_path = os.path.join(self.dash_install_dir, "widgets", "{}.yaml".format(widget_type))

            try:
                #
                # Parse the derived widget definition
                #
                with open(yaml_path, "r") as yamlfd:
                    widget = yamlfd.read()
                final_widget = self._load_yaml(widget)
            except yaml.YAMLError as exc:
                self._log_error(dash, name, "Error in widget definition '%s':".format(widget_type))
                self._log_yaml_dash_error(dash, name, exc)
                return self.error_widget("Error loading widget definition")

            # Substitute variables in the parsed widget definition.
            final_widget, templates = self._do_subs(final_widget, instantiated_widget)

            #
            # Add in global params
            #
            if global_parameters is not None:
                for key in global_parameters:
                    if key == "devices":
                        if widget_type in global_parameters["devices"]:
                            for dkey in global_parameters["devices"][widget_type]:
                                if dkey not in instantiated_widget:
                                    instantiated_widget[dkey] = global_parameters["devices"][widget_type][dkey]
                    else:
                        if key not in instantiated_widget:
                            instantiated_widget[key] = global_parameters[key]

            #
            # Override defaults with parameters in users definition
            #
            for key in instantiated_widget:
                if key != "widget_type" and key not in templates:
                    # if it is an existing key and it is a style attribute, prepend, don't overwrite
                    if key in final_widget and key.find("style") != -1:
                        # if it is an existing key and it is a style attribute, prepend, don't overwrite
                        final_widget[key] = final_widget[key] + ";" + instantiated_widget[key]
                    else:
                        final_widget[key] = instantiated_widget[key]
                    if "fields" in final_widget and key in final_widget["fields"]:
                        final_widget["fields"][key] = instantiated_widget[key]
                    if "css" in final_widget and key in final_widget["css"]:
                        final_widget["css"][key] = final_widget["css"][key] + ";" + instantiated_widget[key]
                    if "static_css" in final_widget and key in final_widget["static_css"]:
                        final_widget["static_css"][key] = (
                            final_widget["static_css"][key] + ";" + instantiated_widget[key]
                        )
                    if "icons" in final_widget and key in final_widget["icons"]:
                        final_widget["icons"][key] = instantiated_widget[key]
                    if "static_icons" in final_widget and key in final_widget["static_icons"]:
                        final_widget["static_icons"][key] = instantiated_widget[key]

            #
            # Process variables from skin
            #
            final_widget = self._resolve_css_params(final_widget, css_vars)
            #
            # Merge styles
            #
            final_widget = self._merge_styles(final_widget, name)
            return final_widget

        except FileNotFoundError:
            self.logger.warning("Unable to find widget type '%s'", widget_type)
            self.logger.warning(traceback.format_exc())
            # Return some valid data so the browser will render a blank widget
            return self.error_widget("Unable to find widget type '{}'".format(widget_type))

    @staticmethod
    def error_widget(error):
        return {"widget_type": "baseerror", "fields": {"err": error}, "static_css": {"widget_style": ""}}

    @staticmethod
    def _widget_exists(widgets, _id):
        for widget in widgets:
            if widget["id"] == _id:
                return True
        return False

    def _add_layout(self, value, layout, occupied, dash, page, includes, css_vars, global_parameters):
        if value is None:
            return
        widget_dimensions = re.compile("^(.+)\\((\\d+)x(\\d+)\\)$")
        value = "".join(value.split())
        widgets = value.split(",")
        column = 1
        for wid in widgets:
            size = widget_dimensions.search(wid)
            if size:
                name = size.group(1)
                xsize = size.group(2)
                ysize = size.group(3)

            elif "widget_size" in dash:
                name = wid
                xsize = dash["widget_size"][0]
                ysize = dash["widget_size"][1]
            else:
                name = wid
                xsize = 1
                ysize = 1

            while "{}x{}".format(column, layout) in occupied:
                column += 1

            if name != "spacer":
                sanitized_name = name.replace(".", "-").replace("_", "-").lower()
                widget = {"id": "{}-{}".format(page, sanitized_name)}

                if self._widget_exists(dash["widgets"], widget["id"]):
                    self.logger.warning("Duplicate widget name '%s' - ignored", name)
                else:
                    widget["position"] = [column, layout]
                    widget["size"] = [xsize, ysize]
                    widget["parameters"] = self._load_widget(dash, includes, name, css_vars, global_parameters)
                    dash["widgets"].append(widget)

            for x in range(column, column + int(xsize)):
                for y in range(layout, layout + int(ysize)):
                    occupied["{}x{}".format(x, y)] = 1
            column += int(xsize)

    @staticmethod
    def _merge_dashes(dash1, dash2):
        for key in dash2:
            if key == "widgets":
                for widget in dash2["widgets"]:
                    dash1["widgets"].append(widget)
            elif key == "errors":
                for error in dash2["errors"]:
                    dash1["errors"].append(error)
            else:
                dash1[key] = dash2[key]

        return dash1

    def _log_error(self, dash, name, error):
        dash["errors"].append("{}: {}".format(os.path.basename(name), error))
        self.logger.warning(error)

    def _log_yaml_error(self, exc):
        for line in self._yaml_error_lines(exc):
            self.logger.warning(line)

    def _log_yaml_dash_error(self, dash, name, exc):
        for line in self._yaml_error_lines(exc):
            self._log_error(dash, name, line)

    @staticmethod
    def _yaml_error_lines(exc):
        lines = []
        if hasattr(exc, "problem_mark"):
            lines.append("parser says")
            lines.append(str(exc.problem_mark))
            if exc.context is not None:
                lines.append(str(exc.problem) + " " + str(exc.context))
            else:
                lines.append(str(exc.problem))
        return lines

    def _load_yaml(self, stream):
        myyaml = None
        yaml.add_constructor("!secret", ha._secret_yaml, Loader=yaml.SafeLoader)
        try:
            myyaml = yaml.load(stream, Loader=yaml.SafeLoader)
        except ValueError as v:
            self.logger.warning(str(v))

        return myyaml

    def _create_dash(self, name, css_vars):
        dash, layout, occupied, includes = self._create_sub_dash(name, "dash", 0, {}, [], 1, css_vars, None)
        return dash

    # noinspection PyBroadException
    def _create_sub_dash(  # noqa: C901
        self, name, extension, layout, occupied, includes, level, css_vars, global_parameters
    ):
        if extension == "dash":
            dash = {"title": "HADashboard", "widget_dimensions": [120, 120], "widget_margins": [5, 5], "columns": 8}
        else:
            dash = {}

        dash["widgets"] = []
        dash["errors"] = []
        valid_params = [
            "title",
            "widget_dimensions",
            "widget_margins",
            "columns",
            "widget_size",
            "rows",
            "namespace",
            "scalable",
        ]
        layouts = []

        if level > self.max_include_depth:
            self._log_error(dash, name, "Maximum include level reached ({})".format(self.max_include_depth))
            return dash, layout, occupied, includes

        dashfile = os.path.join(self.dashboard_dir, "{}.{}".format(name, extension))
        page = "default"

        try:
            with open(dashfile, "r") as yamlfd:
                defs = yamlfd.read()
        except Exception:
            self._log_error(dash, name, "Error opening dashboard file '{}'".format(dashfile))
            return dash, layout, occupied, includes

        try:
            dash_params = self._load_yaml(defs)
        except yaml.YAMLError as exc:
            self._log_error(dash, name, "Error while parsing dashboard '{}':".format(dashfile))
            self._log_yaml_dash_error(dash, name, exc)
            return dash, layout, occupied, includes
        if dash_params is not None:
            if "global_parameters" in dash_params:
                if extension == "dash":
                    global_parameters = dash_params["global_parameters"]
                else:
                    self.logger.warning(
                        "global_parameters dashboard directive illegal in imported dashboard '%s.%s'", name, extension
                    )

            if global_parameters is None:
                global_parameters = {"namespace": "default"}

            if "namespace" not in global_parameters:
                global_parameters["namespace"] = "default"

            for param in dash_params:
                if param == "layout" and dash_params[param] is not None:
                    for lay in dash_params[param]:
                        layouts.append(lay)
                elif param in valid_params:
                    if extension == "dash":
                        dash[param] = dash_params[param]
                    else:
                        self.logger.warning(
                            "Top level dashboard directive illegal in imported dashboard '%s.%s': %s: %s",
                            name,
                            extension,
                            param,
                            dash_params[param],
                        )
                else:
                    includes.append({param: dash_params[param]})

            for lay in layouts:
                if isinstance(lay, dict):
                    if "include" in lay:
                        new_dash, layout, occupied, includes = self._create_sub_dash(
                            os.path.join(self.dashboard_dir, lay["include"]),
                            "yaml",
                            layout,
                            occupied,
                            includes,
                            level + 1,
                            css_vars,
                            global_parameters,
                        )
                        if new_dash is not None:
                            self._merge_dashes(dash, new_dash)
                    elif "empty" in lay:
                        layout += lay["empty"]
                    else:
                        self._log_error(dash, name, "Incorrect directive, should be 'include or empty': {}".format(lay))
                else:
                    layout += 1
                    self._add_layout(lay, layout, occupied, dash, page, includes, css_vars, global_parameters)

        return dash, layout, occupied, includes

    @staticmethod
    def _latest_file(path):
        late_file = datetime.datetime.fromtimestamp(86400)
        for root, subdirs, files in os.walk(path):
            for file in files:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(root, file)))
                if mtime > late_file:
                    late_file = mtime
        return late_file

    # noinspection PyBroadException
    def _get_dash(self, name, skin, skindir):  # noqa C901
        pydashfile = os.path.join(self.dashboard_dir, "{}.pydash".format(name))
        dashfile = os.path.join(self.dashboard_dir, "{}.dash".format(name))

        #
        # Grab CSS Variables
        #
        css_vars = self._load_css_params(skin, skindir)
        if css_vars is None:
            return None
        if os.path.isfile(pydashfile):
            with open(pydashfile, "r") as dashfd:
                dash = ast.literal_eval(dashfd.read())
        elif os.path.isfile(dashfile):
            dash = self._create_dash(name, css_vars)
            if dash is None:
                return None
        else:
            self.logger.warning("Dashboard '%s' not found", name)
            return None

        if "head_includes" in css_vars and css_vars["head_includes"] is not None:
            dash["head_includes"] = css_vars["head_includes"]
        else:
            dash["head_includes"] = []

        #
        # adds custom_javascripts to the head includes if they exist
        #
        custom_js = os.path.join(self.config_dir, "custom_javascript")
        if os.path.isdir(custom_js):
            for filename in os.listdir(custom_js):
                if filename.endswith(".js"):
                    dash["head_includes"].append(
                        '<script type="text/javascript" src="custom_javascript/{}"></script>'.format(filename)
                    )

        if "body_includes" in css_vars and css_vars["body_includes"] is not None:
            dash["body_includes"] = css_vars["body_includes"]
        else:
            dash["body_includes"] = []
        #
        # Load Widgets
        #
        widgets = self._get_widgets()

        css = ""
        js = ""
        rendered_css = None

        widget = None
        try:
            #
            # Base CSS template and compile
            #
            if not os.path.isfile(os.path.join(skindir, "dashboard.css")):
                self.logger.warning("Error loading dashboard.css for skin '%s'", skin)
            else:
                template = os.path.join(skindir, "dashboard.css")
                with open(template, "r") as cssfd:
                    csstemplate = cssfd.read()
                rendered_css, subs = self._do_subs(csstemplate, css_vars)
                css = css + rendered_css + "\n"

            #
            # Template and compile widget CSS
            #
            for widget in dash["widgets"]:
                css_template = Environment(loader=BaseLoader).from_string(
                    widgets[widget["parameters"]["widget_type"]]["css"]
                )
                css_vars["id"] = widget["id"]
                rendered_css = css_template.render(css_vars)

                css = css + rendered_css + "\n"

            for widget in widgets:
                js = js + widgets[widget]["js"] + "\n"

        except KeyError:
            self.logger.warning("Widget type not found: %s", widget["parameters"]["widget_type"])
            return None
        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error in CSS file")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            if rendered_css is not None:
                self.logger.warning("Rendered CSS:")
                self.logger.warning(rendered_css)
                self.logger.warning("-" * 60)
            return None

        if not os.path.exists(os.path.join(self.compiled_css_dir, skin)):
            os.makedirs(os.path.join(self.compiled_css_dir, skin))

        css_path = os.path.join(self.compiled_css_dir, skin, "{}_application.css".format(name.lower()))
        with open(css_path, "w") as css_file:
            css_file.write(css)

        if not os.path.exists(self.compiled_javascript_dir):
            os.makedirs(self.compiled_javascript_dir)

        if not os.path.exists(os.path.join(self.compiled_javascript_dir, skin)):
            os.makedirs(os.path.join(self.compiled_javascript_dir, skin))

        if not os.path.exists(self.compiled_html_dir):
            os.makedirs(self.compiled_html_dir)

        if not os.path.exists(os.path.join(self.compiled_html_dir, skin)):
            os.makedirs(os.path.join(self.compiled_html_dir, skin))

        js_path = os.path.join(self.compiled_javascript_dir, "application.js")
        with open(js_path, "w") as js_file:
            js_file.write(js)

        for widget in dash["widgets"]:
            html = widgets[widget["parameters"]["widget_type"]]["html"].replace("\n", "").replace("\r", "")
            widget["html"] = html

        return dash

    def _get_widgets(self):
        widgets = {}
        for widget_dir in [
            os.path.join(self.dash_install_dir, "widgets"),
            os.path.join(self.config_dir, "custom_widgets"),
        ]:
            # widget_dir = os.path.join(self.dash_install_dir, "widgets")
            if os.path.isdir(widget_dir):
                widget_dirs = os.listdir(path=widget_dir)
                for widget in widget_dirs:
                    if widget_dir == os.path.join(self.config_dir, "custom_widgets"):
                        self.access.info("Loading custom widget '%s'", widget)
                    if os.path.isdir(os.path.join(widget_dir, widget)):
                        jspath = os.path.join(widget_dir, widget, "{}.js".format(widget))
                        csspath = os.path.join(widget_dir, widget, "{}.css".format(widget))
                        htmlpath = os.path.join(widget_dir, widget, "{}.html".format(widget))
                        with open(jspath, "r") as fd:
                            js = fd.read()
                        with open(csspath, "r") as fd:
                            css = fd.read()
                        with open(htmlpath, "r") as fd:
                            html = fd.read()
                        widgets[widget] = {"js": js, "css": css, "html": html}
        return widgets

    def _list_dashes(self):
        if not os.path.isdir(self.dashboard_dir):
            return {}

        files = os.listdir(self.dashboard_dir)
        dash_list = OrderedDict()
        for file in sorted(files):
            if file.endswith(".pydash"):
                name = file.replace(".pydash", "")
                dash_list[name] = "{}/{}".format(self.base_url, name)
            elif file.endswith(".dash"):
                name = file.replace(".dash", "")
                dash_list[name] = "{}/{}".format(self.base_url, name)

        params = {"dash_list": dash_list, "main": "1"}

        return params

    def _conditional_compile(self, name, skin, recompile):

        #
        # Check skin exists
        #
        skindir = os.path.join(self.config_dir, "custom_css", skin)
        if os.path.isdir(skindir):
            self.access.info("Loading custom skin '%s'", skin)
        else:
            # Not a custom skin, try product skins
            skindir = os.path.join(self.css_dir, skin)
            if not os.path.isdir(skindir):
                self.logger.warning("Skin '%s' does not exist", skin)
                skin = "default"
                skindir = os.path.join(self.css_dir, "default")

        if self.dash_force_compile is False:
            do_compile = False

            if recompile is True:
                do_compile = True
            #
            # Check if compiled versions even exist and get their timestamps.
            #
            last_compiled = datetime.datetime.now()
            for file in [
                os.path.join(self.compiled_css_dir, skin, "{}_application.css".format(name.lower())),
                os.path.join(self.compiled_javascript_dir, "application.js"),
                os.path.join(self.compiled_javascript_dir, skin, "{}_init.js".format(name.lower())),
                os.path.join(self.compiled_html_dir, skin, "{}_head.html".format(name.lower())),
                os.path.join(self.compiled_html_dir, skin, "{}_body.html".format(name.lower())),
            ]:
                if not os.path.isfile(file):
                    do_compile = True

                try:
                    mtime = os.path.getmtime(file)
                except OSError:
                    mtime = 86400
                last_modified_date = datetime.datetime.fromtimestamp(mtime)
                if last_modified_date < last_compiled:
                    last_compiled = last_modified_date

            widget_mod = self._latest_file(os.path.join(self.dash_install_dir, "widgets"))
            custom_widget_mod = self._latest_file(os.path.join(self.config_dir, "custom_widgets"))
            skin_mod = self._latest_file(skindir)
            dash_mod = self._latest_file(self.dashboard_dir)

            if (
                custom_widget_mod > last_compiled
                or widget_mod > last_compiled
                or skin_mod > last_compiled
                or dash_mod > last_compiled
            ):
                do_compile = True

            # Force compilation at startup

            if self.start_time > last_compiled and self.dash_compile_on_start is True:
                do_compile = True

            if do_compile is False:
                return {"errors": []}

        self.access.info("Compiling dashboard '%s'", name)

        dash = self._get_dash(name, skin, skindir)
        if dash is None:
            dash_list = self._list_dashes()
            return {"errors": ["Dashboard has errors or is not found - check log for details"], "dash_list": dash_list}

        params = dash
        params["base_url"] = self.base_url
        params["name"] = name.lower()
        params["skin"] = skin
        params["transport"] = self.transport

        #
        # Build dash specific code
        #
        env = Environment(loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"]))

        template = env.get_template("dashinit.jinja2")
        rendered_template = template.render(params)
        js_path = os.path.join(self.compiled_javascript_dir, skin, "{}_init.js".format(name.lower()))
        with open(js_path, "w") as js_file:
            js_file.write(rendered_template)

        template = env.get_template("head_include.jinja2")
        rendered_template = template.render(params)
        js_path = os.path.join(self.compiled_html_dir, skin, "{}_head.html".format(name.lower()))
        with open(js_path, "w") as js_file:
            js_file.write(rendered_template)

        template = env.get_template("body_include.jinja2")
        rendered_template = template.render(params)
        js_path = os.path.join(self.compiled_html_dir, skin, "{}_body.html".format(name.lower()))
        with open(js_path, "w") as js_file:
            js_file.write(rendered_template)

        return dash

    #
    # Methods
    #

    @_profile_this
    @_timeit
    def get_dashboard(self, name, skin, recompile):

        try:

            dash = self._conditional_compile(name, skin, recompile)

            if dash is None:
                errors = ["An unrecoverable error occurred - check log for details"]
            else:
                errors = dash["errors"]

            if "widgets" in dash:
                widgets = dash["widgets"]
            else:
                widgets = {}

            if "scalable" in dash:
                scalable = dash["scalable"]
            else:
                scalable = True

            if "dash_list" in dash and dash["dash_list"] != {}:
                dash_list = dash["dash_list"]["dash_list"]
            else:
                dash_list = []

            # add errors if we got any
            if errors:
                params = {"title": self.title, "errors": errors, "name": name.lower(), "dash_list": dash_list}

                env = Environment(
                    loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"])
                )

                template = env.get_template("list.jinja2")
                rendered_template = template.render(params)
            else:
                include_path = os.path.join(self.compiled_html_dir, skin, "{}_head.html".format(name.lower()))
                with open(include_path, "r") as include_file:
                    head_includes = include_file.read()
                include_path = os.path.join(self.compiled_html_dir, skin, "{}_body.html".format(name.lower()))
                with open(include_path, "r") as include_file:
                    body_includes = include_file.read()

                #
                # return params
                #
                params = {
                    "title": self.title,
                    "errors": errors,
                    "name": name.lower(),
                    "skin": skin,
                    "widgets": widgets,
                    "head_includes": head_includes,
                    "body_includes": body_includes,
                    "scalable": scalable,
                    "fa4compatibility": self.fa4compatibility,
                    "transport": self.transport,
                }

                env = Environment(
                    loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"])
                )

                template = env.get_template("dashboard.jinja2")
                rendered_template = template.render(params)

            return rendered_template

        except Exception:
            self.logger.warning("-" * 60)
            self.logger.warning("Unexpected error during DASH creation")
            self.logger.warning("-" * 60)
            self.logger.warning(traceback.format_exc())
            self.logger.warning("-" * 60)
            return self.html_error()

    def html_error(self):
        params = {"errors": ["An unrecoverable error occurred fetching dashboard, check log for details"]}
        env = Environment(loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"]))

        template = env.get_template("list.jinja2")
        rendered_template = template.render(params)

        return rendered_template

    def get_dashboard_list(self, paramOverwrite=None):

        if paramOverwrite is None:
            dash = self._list_dashes()
        else:
            dash = paramOverwrite

        env = Environment(loader=FileSystemLoader(self.template_dir), autoescape=select_autoescape(["html", "xml"]))

        template = env.get_template("list.jinja2")
        rendered_template = template.render(dash)

        return rendered_template
