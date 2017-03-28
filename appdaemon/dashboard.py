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

import appdaemon.homeassistant as ha
import appdaemon.conf as conf


def profile_this(fn):
    def profiled_fn(*args, **kwargs):

        pr = None
        if conf.profile_dashboard:
            pr = cProfile.Profile()
            pr.enable()

        dash = fn(*args, **kwargs)

        if conf.profile_dashboard:
            pr.disable()
            s = io.StringIO()
            sortby = 'cumulative'
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            print(s.getvalue())
        return dash

    return profiled_fn


def timeit(func):
    @functools.wraps(func)
    def newfunc(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        ha.log(conf.dash, "INFO", 'function [{}] finished in {} ms'.format(
            func.__name__, int(elapsed_time * 1000)))
        return result

    return newfunc


# noinspection PyUnresolvedReferences,PyUnresolvedReferences,PyUnresolvedReferences,PyUnresolvedReferences
def load_css_params(skin, skindir):
    yaml_path = os.path.join(skindir, "variables.yaml")
    if os.path.isfile(yaml_path):
        with open(yaml_path, 'r') as yamlfd:
            css_text = yamlfd.read()
        try:
            css = yaml.load(css_text)
        except yaml.YAMLError as exc:
            ha.log(conf.dash, "WARNING", "Error loading CSS variables")
            if hasattr(exc, 'problem_mark'):
                if exc.context is not None:
                    ha.log(conf.dash, "WARNING", "parser says")
                    ha.log(conf.dash, "WARNING", str(exc.problem_mark))
                    ha.log(conf.dash, "WARNING", str(exc.problem) + " " + str(exc.context))
                else:
                    ha.log(conf.dash, "WARNING", "parser says")
                    ha.log(conf.dash, "WARNING", str(exc.problem_mark))
                    ha.log(conf.dash, "WARNING", str(exc.problem))
            return None
        if css is None:
            return {}
        else:
            return expand_vars(css, css)
    else:
        ha.log(conf.dash, "WARNING", "Error loading variables.yaml for skin '{}'".format(skin))
        return None


def expand_vars(fields, subs):
    done = False
    variable = re.compile("\$(\w+)")
    index = 0
    while not done and index < 100:
        index += 1
        done = True
        for varline in fields:
            if isinstance(fields[varline], dict):
                fields[varline] = expand_vars(fields[varline], subs)
            elif fields[varline] is not None and type(fields[varline]) == str:
                _vars = variable.finditer(fields[varline])
                for var in _vars:
                    subvar = var.group()[1:]
                    if subvar in subs:
                        done = False
                        fields[varline] = fields[varline].replace(var.group(), subs[subvar], 1)
                    else:
                        ha.log(conf.dash, "WARNING",
                               "Variable definition not found in CSS Skin variables: ${}".format(subvar))
                        fields[varline] = ""

    if index == 100:
        ha.log(conf.dash, "WARNING", "Unable to resolve CSS Skin variables, check for circular references")

    return fields


def get_styles(style_str, name, field):
    #
    # Parse styles in order from a string and allow later entries to override earlier ones
    #
    result = {}
    styles = style_str.split(";")
    for style in styles:
        if style != "" and style is not None:
            pieces = style.split(":")
            if len(pieces) == 2:
                result[pieces[0].strip()] = pieces[1]
            else:
                ha.log(conf.dash, "WARNING",
                       "malformed CSS: {} in widget '{}', field '{}' (could be a problem in the skin) - ignoring".
                       format(style, name, field))

    return result


def merge_styles(widget, name):
    result = {}
    for key in widget:
        if key == "css" or key == "static_css":
            result[key] = merge_styles(widget[key], name)
        elif key.find("style") == -1:
            result[key] = widget[key]
        else:
            line = ""
            styles = get_styles(widget[key], name, key)
            for style in styles:
                line = line + style + ":" + styles[style] + ";"
            result[key] = line
    return result


def do_subs(file, _vars, blank):
    sub = re.compile("\{\{(.+)\}\}")
    templates = {}
    result = ""
    with open(file, 'r') as fd:
        for line in fd:
            for ikey in _vars:
                match = "{{{{{}}}}}".format(ikey)
                if match in line:
                    templates[ikey] = 1
                    line = line.replace(match, _vars[ikey])

            line = sub.sub(blank, line)

            result += line
    return result, templates


# noinspection PyUnresolvedReferences
def load_widget(dash, includes, name, css_vars, global_parameters):
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
        yaml_path = os.path.join(conf.dashboard_dir, "{}.yaml".format(name))
        if os.path.isfile(yaml_path):
            with open(yaml_path, 'r') as yamlfd:
                widget = yamlfd.read()
            try:
                instantiated_widget = yaml.load(widget)
            except yaml.YAMLError as exc:
                log_error(dash, name, "Error while parsing dashboard '{}':".format(yaml_path))
                if hasattr(exc, 'problem_mark'):
                    if exc.context is not None:
                        log_error(dash, name, "parser says")
                        log_error(dash, name, str(exc.problem_mark))
                        log_error(dash, name, str(exc.problem) + " " + str(exc.context))
                    else:
                        log_error(dash, name, "parser says")
                        log_error(dash, name, str(exc.problem_mark))
                        log_error(dash, name, str(exc.problem))
                return {"widget_type": "text", "title": "Error loading widget"}

        elif name.find(".") != -1:
            #
            # No file, check if it is implicitly defined via an entity id
            #
            parts = name.split(".")
            instantiated_widget = {"widget_type": parts[0], "entity": name, "title_is_friendly_name": 1}
        else:
            ha.log(conf.dash, "WARNING", "Unable to find widget definition for '{}'".format(name))
            # Return some valid data so the browser will render a blank widget
            return {"widget_type": "text", "title": "Widget definition not found"}

    widget_type = None
    try:
        if "widget_type" not in instantiated_widget:
            return {"widget_type": "text", "title": "Widget type not specified"}

        #
        # One way or another we now have the widget definition
        #
        widget_type = instantiated_widget["widget_type"]

        if widget_type == "text_sensor":
            ha.log(conf.dash, "WARNING",
                   "'text_sensor' widget is deprecated, please use 'sensor' instead for widget '{}'".format(name))
        if os.path.isdir(os.path.join(conf.dash_dir, "widgets", widget_type)):
            # This is a base widget so return it in full
            return expand_vars(instantiated_widget, css_vars)

        # We are working with a derived widget so we need to do some merges and substitutions

        yaml_path = os.path.join(conf.dash_dir, "widgets", "{}.yaml".format(widget_type))

        #
        # Variable substitutions
        #
        yaml_file, templates = do_subs(yaml_path, instantiated_widget, '""')

        try:
            #
            # Parse the substituted YAML file - this is a derived widget definition
            #
            final_widget = yaml.load(yaml_file)
        except yaml.YAMLError as exc:
            log_error(dash, name, "Error in widget definition '{}':".format(widget_type))
            if hasattr(exc, 'problem_mark'):
                if exc.context is not None:
                    log_error(dash, name, "parser says")
                    log_error(dash, name, str(exc.problem_mark))
                    log_error(dash, name, str(exc.problem) + " " + str(exc.context))
                else:
                    log_error(dash, name, "parser says")
                    log_error(dash, name, str(exc.problem_mark))
                    log_error(dash, name, str(exc.problem))
            return {"widget_type": "text", "title": "Error loading widget definition"}

        #
        # Add in global params
        #
        if global_parameters is not None:
            for key in global_parameters:
                final_widget[key] = global_parameters[key]

        #
        # Override defaults with parameters in users definition
        #
        for key in instantiated_widget:
            if key != "widget_type" and key not in templates:
                # if it is an existing key and it is a style attribute, prepend, don't overwrite
                if key in final_widget and key.find("style") != -1:
                    # if it is an existing key and it is a style attirpute, prepend, don't overwrite
                    final_widget[key] = final_widget[key] + ";" + instantiated_widget[key]
                else:
                    final_widget[key] = instantiated_widget[key]
                if "css" in final_widget and key in final_widget["css"]:
                    final_widget["css"][key] = final_widget["css"][key] + ";" + instantiated_widget[key]
                if "static_css" in final_widget and key in final_widget["static_css"]:
                    final_widget["static_css"][key] = final_widget["static_css"][key] + ";" + instantiated_widget[key]
                if "icons" in final_widget and key in final_widget["icons"]:
                    final_widget["icons"][key] = instantiated_widget[key]
                if "static_icons" in final_widget and key in final_widget["static_icons"]:
                    final_widget["static_icons"][key] = instantiated_widget[key]

        #
        # Process variables from skin
        #
        final_widget = expand_vars(final_widget, css_vars)
        #
        # Merge styles
        #
        final_widget = merge_styles(final_widget, name)

        return final_widget
    except FileNotFoundError:
        ha.log(conf.dash, "WARNING", "Unable to find widget type '{}'".format(widget_type))
        # Return some valid data so the browser will render a blank widget
        return {"widget_type": "text", "title": "Widget type not found"}


def widget_exists(widgets, _id):
    for widge in widgets:
        if widge["id"] == _id:
            return True
    return False


def add_layout(value, layout, occupied, dash, page, includes, css_vars, global_parameters):
    if value is None:
        return
    widgetdimensions = re.compile("^(.+)\\((\d+)x(\d+)\\)$")
    value = ''.join(value.split())
    widgets = value.split(",")
    column = 1
    for wid in widgets:
        size = widgetdimensions.search(wid)
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
            widget = {}
            widget["id"] = "{}-{}".format(page, sanitized_name)

            if widget_exists(dash["widgets"], widget["id"]):
                ha.log(conf.dash, "WARNING", "Duplicate widget name '{}' - ignored".format(name))
            else:
                widget["position"] = [column, layout]
                widget["size"] = [xsize, ysize]
                widget["parameters"] = load_widget(dash, includes, name, css_vars, global_parameters)
                dash["widgets"].append(widget)

        for x in range(column, column + int(xsize)):
            for y in range(layout, layout + int(ysize)):
                occupied["{}x{}".format(x, y)] = 1
        column += int(xsize)


def merge_dashes(dash1, dash2):
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


def load_dash(name, css_vars):
    dash, layout, occupied, includes = _load_dash(name, "dash", 0, {}, [], 1, css_vars, None)
    return dash


def log_error(dash, name, error):
    dash["errors"].append("{}: {}".format(os.path.basename(name), error))
    ha.log(conf.dash, "WARNING", error)


# noinspection PyBroadException
def _load_dash(name, extension, layout, occupied, includes, level, css_vars, global_parameters):
    if extension == "dash":
        dash = {"title": "HADashboard", "widget_dimensions": [120, 120], "widget_margins": [5, 5], "columns": 8}
    else:
        dash = {}

    dash["widgets"] = []
    dash["errors"] = []
    valid_params = ["title", "widget_dimensions", "widget_margins", "columns", "widget_size"]
    layouts = []

    if level > conf.max_include_depth:
        log_error(dash, name, "Maximum include level reached ({})".format(conf.max_include_depth))
        return dash, layout, occupied, includes

    dashfile = os.path.join(conf.dashboard_dir, "{}.{}".format(name, extension))
    page = "default"

    try:
        with open(dashfile, 'r') as yamlfd:
            defs = yamlfd.read()
    except:
        log_error(dash, name, "Error opening dashboard file '{}'".format(dashfile))
        return dash, layout, occupied, includes

    try:
        dash_params = yaml.load(defs, yaml.SafeLoader)
    except yaml.YAMLError as exc:
        log_error(dash, name, "Error while parsing dashboard '{}':".format(dashfile))
        if hasattr(exc, 'problem_mark'):
            if exc.context is not None:
                log_error(dash, name, "parser says")
                log_error(dash, name, str(exc.problem_mark))
                log_error(dash, name, str(exc.problem) + " " + str(exc.context))
            else:
                log_error(dash, name, "parser says")
                log_error(dash, name, str(exc.problem_mark))
                log_error(dash, name, str(exc.problem))
        else:
            log_error(dash, name, "Something went wrong while parsing dashboard file")

        return dash, layout, occupied, includes
    if dash_params is not None:
        if "global_parameters" in dash_params:
            if extension == "dash":
                global_parameters = dash_params["global_parameters"]
            else:
                ha.log(conf.dash, "WARNING",
                       "global_parameters dashboard directive illegal in imported dashboard '{}.{}'".
                       format(name, extension))

        for param in dash_params:
            if param == "layout" and dash_params[param] is not None:
                for lay in dash_params[param]:
                    layouts.append(lay)
            elif param in valid_params:
                if extension == "dash":
                    dash[param] = dash_params[param]
                else:
                    ha.log(conf.dash, "WARNING",
                           "Top level dashboard directive illegal in imported dashboard '{}.{}': {}: {}".
                           format(name, extension, param, dash_params[param]))
            else:
                includes.append({param: dash_params[param]})

        for lay in layouts:
            if isinstance(lay, dict):
                if "include" in lay:
                    new_dash, layout, occupied, includes = _load_dash(
                        os.path.join(conf.dashboard_dir, lay["include"]),
                        "yaml", layout, occupied, includes, level + 1, css_vars, global_parameters)
                    if new_dash is not None:
                        merge_dashes(dash, new_dash)
                elif "empty" in lay:
                    layout += lay["empty"]
                else:
                    log_error(dash, name, "Incorrect directive, should be 'include or empty': {}".format(lay))
            else:
                layout += 1
                add_layout(lay, layout, occupied, dash, page, includes, css_vars, global_parameters)

    return dash, layout, occupied, includes


def latest_file(path):
    late_file = datetime.datetime.fromtimestamp(0)
    for root, subdirs, files in os.walk(path):
        for file in files:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(root, file)))
            if mtime > late_file:
                late_file = mtime
    return late_file


@profile_this
@timeit
def compile_dash(name, skin, skindir, params):
    if conf.dash_force_compile is False:
        do_compile = False

        if "recompile" in params:
            do_compile = True
        #
        # Check if compiled versions even exist and get their timestamps.
        #
        last_compiled = datetime.datetime.now()
        for file in [
            os.path.join(conf.compiled_css_dir, skin, "{}_application.css".format(name.lower())),
            os.path.join(conf.compiled_javascript_dir, "application.js"),
            os.path.join(conf.compiled_javascript_dir, skin, "{}_init.js".format(name.lower())),
            os.path.join(conf.compiled_html_dir, skin, "{}_head.html".format(name.lower())),
            os.path.join(conf.compiled_html_dir, skin, "{}_body.html".format(name.lower())),
        ]:
            if not os.path.isfile(file):
                do_compile = True

            try:
                mtime = os.path.getmtime(file)
            except OSError:
                mtime = 0
            last_modified_date = datetime.datetime.fromtimestamp(mtime)
            if last_modified_date < last_compiled:
                last_compiled = last_modified_date

        widget_mod = latest_file(os.path.join(conf.dash_dir, "widgets"))
        skin_mod = latest_file(skindir)
        dash_mod = latest_file(conf.dashboard_dir)

        if widget_mod > last_compiled or skin_mod > last_compiled or dash_mod > last_compiled:
            do_compile = True

        # Force compilation at startup

        if conf.start_time > last_compiled and conf.dash_compile_on_start is True:
            do_compile = True

        if do_compile is False:
            return {"errors": []}

    ha.log(conf.dash, "INFO", "Compiling dashboard '{}'".format(name))

    dash = get_dash(name, skin, skindir)
    if dash is None:
        dash_list = list_dashes()
        return {"errors": ["Dashboard has errors or is not found - check log for details"], "dash_list": dash_list}

    params = dash
    params["stream_url"] = conf.stream_url
    params["base_url"] = conf.base_url
    params["name"] = name.lower()
    params["skin"] = skin

    #
    # Build dash specific code
    #
    env = Environment(
        loader=FileSystemLoader(conf.template_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )

    template = env.get_template("dashinit.jinja2")
    rendered_template = template.render(params)
    js_path = os.path.join(conf.compiled_javascript_dir, skin, "{}_init.js".format(name.lower()))
    with open(js_path, "w") as js_file:
        js_file.write(rendered_template)

    template = env.get_template("head_include.jinja2")
    rendered_template = template.render(params)
    js_path = os.path.join(conf.compiled_html_dir, skin, "{}_head.html".format(name.lower()))
    with open(js_path, "w") as js_file:
        js_file.write(rendered_template)

    template = env.get_template("body_include.jinja2")
    rendered_template = template.render(params)
    js_path = os.path.join(conf.compiled_html_dir, skin, "{}_body.html".format(name.lower()))
    with open(js_path, "w") as js_file:
        js_file.write(rendered_template)



    return dash


# noinspection PyBroadException
def get_dash(name, skin, skindir):
    pydashfile = os.path.join(conf.dashboard_dir, "{}.pydash".format(name))
    dashfile = os.path.join(conf.dashboard_dir, "{}.dash".format(name))

    #
    # Grab CSS Variables
    #
    css_vars = load_css_params(skin, skindir)
    if css_vars is None:
        return None
    if os.path.isfile(pydashfile):
        with open(pydashfile, 'r') as dashfd:
            dash = ast.literal_eval(dashfd.read())
    elif os.path.isfile(dashfile):
        dash = load_dash(name, css_vars)
        if dash is None:
            return None
    else:
        ha.log(conf.dash, "WARNING", "Dashboard '{}' not found".format(name))
        return None

    if "head_includes" in css_vars and css_vars["head_includes"] is not None:
        dash["head_includes"] = css_vars["head_includes"]
    else:
        dash["head_includes"] = []
    if "body_includes" in css_vars and css_vars["body_includes"] is not None:
        dash["body_includes"] = css_vars["body_includes"]
    else:
        dash["body_includes"] = []
    #
    # Load Widgets
    #
    widgets = get_widgets()

    css = ""
    js = ""
    rendered_css = None

    widget = None
    try:
        #
        # Base CSS template and compile
        #
        if not os.path.isfile(os.path.join(skindir, "dashboard.css")):
            ha.log(conf.dash, "WARNING", "Error loading dashboard.css for skin '{}'".format(skin))
        else:
            template = os.path.join(skindir, "dashboard.css")
            rendered_css, subs = do_subs(template, css_vars, "")

            css = css + rendered_css + "\n"

        #
        # Template and compile widget CSS
        #
        for widget in dash["widgets"]:
            css_template = Environment(loader=BaseLoader).from_string(
                widgets[widget["parameters"]["widget_type"]]["css"])
            css_vars["id"] = widget["id"]
            rendered_css = css_template.render(css_vars)

            css = css + rendered_css + "\n"

        for widget in widgets:
            js = js + widgets[widget]["js"] + "\n"

    except KeyError:
        ha.log(conf.dash, "WARNING", "Widget type not found: {}".format(widget["parameters"]["widget_type"]))
        return None
    except:
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", "Unexpected error in CSS file")
        ha.log(conf.dash, "WARNING", '-' * 60)
        ha.log(conf.dash, "WARNING", traceback.format_exc())
        ha.log(conf.dash, "WARNING", '-' * 60)
        if rendered_css is not None:
            ha.log(conf.dash, "WARNING", "Rendered CSS:")
            ha.log(conf.dash, "WARNING", rendered_css)
            ha.log(conf.dash, "WARNING", '-' * 60)
        return None

    if not os.path.exists(os.path.join(conf.compiled_css_dir, skin)):
        os.makedirs(os.path.join(conf.compiled_css_dir, skin))

    css_path = os.path.join(conf.compiled_css_dir, skin, "{}_application.css".format(name.lower()))
    with open(css_path, "w") as css_file:
        css_file.write(css)

    if not os.path.exists(conf.compiled_javascript_dir):
        os.makedirs(conf.compiled_javascript_dir)

    if not os.path.exists(os.path.join(conf.compiled_javascript_dir, skin)):
        os.makedirs(os.path.join(conf.compiled_javascript_dir, skin))

    if not os.path.exists(conf.compiled_html_dir):
        os.makedirs(conf.compiled_html_dir)

    if not os.path.exists(os.path.join(conf.compiled_html_dir, skin)):
        os.makedirs(os.path.join(conf.compiled_html_dir, skin))


    js_path = os.path.join(conf.compiled_javascript_dir, "application.js")
    with open(js_path, "w") as js_file:
        js_file.write(js)

    for widget in dash["widgets"]:
        html = widgets[widget["parameters"]["widget_type"]]["html"].replace('\n', '').replace('\r', '')
        widget["html"] = html

    return dash


def list_dashes():
    if not os.path.isdir(conf.dashboard_dir):
        return {}

    files = os.listdir(conf.dashboard_dir)
    dash_list = {}
    for file in files:
        if file.endswith('.pydash'):
            name = file.replace('.pydash', '')
            dash_list[name] = "{}/{}".format(conf.base_url, name)
        elif file.endswith('.dash'):
            name = file.replace('.dash', '')
            dash_list[name] = "{}/{}".format(conf.base_url, name)
    return dash_list


def get_widgets():
    widget_dir = os.path.join(conf.dash_dir, "widgets")
    widget_dirs = os.listdir(path=widget_dir)
    widgets = {}
    for widget in widget_dirs:
        if os.path.isdir(os.path.join(widget_dir, widget)):
            jspath = os.path.join(widget_dir, widget, "{}.js".format(widget))
            csspath = os.path.join(widget_dir, widget, "{}.css".format(widget))
            htmlpath = os.path.join(widget_dir, widget, "{}.html".format(widget))
            with open(jspath, 'r') as fd:
                js = fd.read()
            with open(csspath, 'r') as fd:
                css = fd.read()
            with open(htmlpath, 'r') as fd:
                html = fd.read()
            widgets[widget] = {"js": js, "css": css, "html": html}
    return widgets
