import os
import ast
import re
import yaml
import sys
import jinja2
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
        startTime = time.time()
        result = func(*args, **kwargs)
        elapsedTime = time.time() - startTime
        ha.log(conf.logger, "INFO",'function [{}] finished in {} ms'.format(
            func.__name__, int(elapsedTime * 1000)))
        return result
    return newfunc

def load_css_params(skin, skindir):
    yaml_path = os.path.join(skindir, "variables.yaml")
    if os.path.isfile(yaml_path):
        with open(yaml_path, 'r') as yamlfd:
            css_text = yamlfd.read()
        try:
            css = yaml.load(css_text)
        except yaml.YAMLError as exc:
            ha.log(conf.logger, "WARNING",  "Error loading CSS variables")
            if hasattr(exc, 'problem_mark'):
                if exc.context != None:
                    ha.log(conf.logger, "WARNING", "parser says")
                    ha.log(conf.logger, "WARNING", str(exc.problem_mark))  
                    ha.log(conf.logger, "WARNING", str(exc.problem) + " " + str(exc.context))
                else:
                    ha.log(conf.logger, "WARNING", "parser says")
                    ha.log(conf.logger, "WARNING", str(exc.problem_mark))
                    ha.log(conf.logger, "WARNING", str(exc.problem)) 
            return None
            
    return expand_vars(css, css)

def expand_vars(fields, subs):
    done = False
    variable = re.compile("\$(\w+)")
    index = 0
    while not done and index < 100:
        index = index + 1
        done = True
        for varline in fields:
            if fields[varline] != None and type(fields[varline]) == str:
                vars = variable.finditer(fields[varline])
                for var in vars:
                    subvar = var.group()[1:]
                    if subvar in subs:
                        done = False
                        fields[varline] = fields[varline].replace(var.group(), subs[subvar], 1)
                    else:
                        ha.log(conf.logger, "WARNING",  "Variable definition not found in CSS Skin variables: ${}".format(subvar))
                        None
    if index == 100:
        ha.log(conf.logger, "WARNING",  "Unable to resolve CSS Skin variables, check for circular references") 
    return fields

def load_widget(dash, includes, name, css_vars):
    instantiated_widget = None
    for include in includes:
        if name in include:
            instantiated_widget = include[name]
            
    if instantiated_widget == None:
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
                    if exc.context != None:
                        log_error(dash, name, "parser says")
                        log_error(dash, name, str(exc.problem_mark))  
                        log_error(dash, name, str(exc.problem) + " " + str(exc.context))
                    else:
                        log_error(dash, name, "parser says")
                        log_error(dash, name, str(exc.problem_mark))
                        log_error(dash, name, str(exc.problem))
                return {"widget_type": "text", "title": "Error loading widget"}
                
        elif name.find(".") != -1:
            parts = name.split(".")
            instantiated_widget = {"widget_type": parts[0], "entity": name, "title_is_friendly_name": 1}
        else:
            ha.log(conf.logger, "WARNING", "Unable to find widget definition for '{}'".format(name))
            # Return some valid data so the browser will render a blank widget
            return {"widget_type": "text", "title": "Widget definition not found"}
                
    try:
        if "widget_type" not in instantiated_widget:
            return {"widget_type": "text", "title": "Widget type not specified"}
        widget_type = instantiated_widget["widget_type"]
        if os.path.isdir(os.path.join(conf.dash_dir, "widgets", widget_type)):
            # This is a base widget so return it in full
            return expand_vars(instantiated_widget, css_vars)
            
        # We are working with a derived widget so we need to do some merges and substitutions
        
        yaml_path = os.path.join(conf.dash_dir, "widgets", "{}.yaml".format(widget_type))
        
        yaml_file = ""
        templates = {}
        sub = re.compile("\{\{(.+)\}\}")

        #size = widgetdimensions.search(wid)
        #if size:
        with open(yaml_path, 'r') as yamlfd:
            for line in yamlfd:
                for ikey in instantiated_widget:
                    newline = ""
                    match = "{{{{{}}}}}".format(ikey)
                    if match in line:
                        templates[ikey] = 1
                        line = line.replace(match, instantiated_widget[ikey])
            
                var = sub.search(line)
                if var:
                    return {"widget_type": "text", "title": "Missing argument in widget definition: {}".format(var.group(1))}
                    
                yaml_file = yaml_file + line

        try:
            final_widget = yaml.load(yaml_file)
        except yaml.YAMLError as exc:
            log_error(dash, name, "Error in widget definition '{}':".format(widget_type))
            if hasattr(exc, 'problem_mark'):
                if exc.context != None:
                    log_error(dash, name, "parser says")
                    log_error(dash, name, str(exc.problem_mark))  
                    log_error(dash, name, str(exc.problem) + " " + str(exc.context))
                else:
                    log_error(dash, name, "parser says")
                    log_error(dash, name, str(exc.problem_mark))
                    log_error(dash, name, str(exc.problem))
            return {"widget_type": "text", "title": "Error loading widget definition"}

        
        for key in instantiated_widget:
            if key != "widget_type" and not key in templates:
                final_widget[key] = instantiated_widget[key]

        final_widget = expand_vars(final_widget, css_vars)
                
                
        return final_widget
    except FileNotFoundError:
        ha.log(conf.logger, "WARNING", "Unable to find widget type '{}'".format(widget_type))
        # Return some valid data so the browser will render a blank widget
        return {"widget_type": "text", "title": "Widget type not found"}
 
def widget_exists(widgets, id):
    for widge in widgets:
        if widge["id"] == id:
            return True
    return False
 
def add_layout(value, layout, occupied, dash, page, includes, css_vars):
    if value == None:
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
                
        else:
            name = wid
            xsize = 1
            ysize = 1
        
        while "{}x{}".format(column, layout) in occupied:
            column = column + 1
        
        if name != "spacer":
            sanitized_name = name.replace(".", "-").replace("_", "-").lower()
            widget = {}
            widget["id"] = "{}-{}".format(page, sanitized_name)
            
            if widget_exists(dash["widgets"], widget["id"]):
                ha.log(conf.logger, "WARNING", "Duplicate widget name '{}' - ignored".format(name))
            else:
                widget["position"] = [column, layout]
                widget["size"] = [xsize, ysize]
                widget["parameters"] = load_widget(dash, includes, name, css_vars)
                dash["widgets"].append(widget)
    
        for x in range(column, column + int(xsize)):
            for y in range(layout, layout + int(ysize)):
                occupied["{}x{}".format(x, y)] = 1
        column = column + int(xsize)

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
    dash, layout, occupied, includes = _load_dash(name, "dash", 0, {}, [], 1, css_vars)
    return(dash)

def log_error(dash, name, error):
    dash["errors"].append("{}: {}".format(os.path.basename(name), error))
    ha.log(conf.logger, "WARNING", error)
    
def _load_dash(name, extension, layout, occupied, includes, level, css_vars):

    if extension == "dash":
        dash = {"title": "HADashboard", "widget_dimensions": [120, 120], "widget_margins": [5, 5], "columns": 8}
    else:
        dash = {}
            
    dash["widgets"] = []
    dash["errors"] = []
    valid_params = ["title", "widget_dimensions", "widget_margins", "columns"]
    layouts = []

    if level > conf.max_include_depth:
        log_error(dash, name, "Maximum include level reached ({})". format(conf.max_include_depth))  
        return dash, layout, occupied, includes
        
    dashfile = os.path.join(conf.dashboard_dir, "{}.{}".format(name, extension))
    page = "default"

    try:
        with open(dashfile, 'r') as yamlfd:
            defs = yamlfd.read()
    except:
        log_error(dash, name, "Error while loading dashboard '{}'".format(dashfile))
        return dash, layout, occupied, includes
        
    try:
        stuff = yaml.load(defs, yaml.SafeLoader)
    except yaml.YAMLError as exc:
        log_error(dash, name, "Error while parsing dashboard '{}':".format(dashfile))
        if hasattr(exc, 'problem_mark'):
            if exc.context != None:
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
    
    if stuff != None:
        for thing in stuff:
            if thing == "layout" and stuff[thing] != None:
                for lay in stuff[thing]:
                    layouts.append(lay)
            elif thing in valid_params:
                if extension == "dash":
                    dash[thing] = stuff[thing]
                else:
                    ha.log(conf.logger, "WARNING", "Top level dashboard directive illegal in imported dashboard '{}.{}': {}: {}".format(name, extension, thing, stuff[thing]))
            else:
                includes.append({thing: stuff[thing]})
        
        for lay in layouts:
            if isinstance(lay, dict):
                if "include" in lay:
                    new_dash, layout, occupied, includes = _load_dash(
                        os.path.join(conf.dashboard_dir, lay["include"]), 
                        "yaml", layout, occupied, includes, level + 1, css_vars)
                    if new_dash != None:
                        merge_dashes(dash, new_dash)
                else:
                   log_error(dash, name, "Incorrect directive, should be 'include': {}".format(lay)) 
            else:
                layout = layout + 1
                add_layout(lay, layout, occupied, dash, page, includes, css_vars)
                    
    return dash, layout, occupied, includes

def latest_file(path):
    latest_file = datetime.datetime.fromtimestamp(0)
    for root, subdirs, files in os.walk(path):
        for file in files:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(root, file)))
            if mtime > latest_file:
                latest_file = mtime
    return(latest_file)
    
@profile_this
@timeit
def compile_dash(name, skin, skindir, params):

    if conf.dash_force_compile is False:
        compile = False
        
        if "recompile" in params:
            compile = True
        #
        # Check if compiled versions even exist and get their timestamps.
        #
        last_compiled = datetime.datetime.now()
        for file in [
                     os.path.join(conf.compiled_css_dir, skin, "{}_application.css".format(name.lower())),
                     os.path.join(conf.compiled_javascript_dir, "application.js"),   
                     os.path.join(conf.compiled_javascript_dir, "{}_init.js".format(name.lower())),
                    ]:
            if not os.path.isfile(file):
                compile = True
            
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
            compile = True

        if conf.start_time > last_compiled:
            compile = True
               
        if compile is False:
            return {"errors": []}
    
    ha.log(conf.logger, "INFO", "Compiling dashboard '{}'".format(name))
    
    dash = get_dash(name, skin, skindir)
    if dash == None:
        dash_list = list_dashes()
        return {"errors":["Dashboard has errors or is not found - check log for details"], "dash_list": dash_list}
        
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
    
    js_path = os.path.join(conf.compiled_javascript_dir, "{}_init.js".format(name.lower()))
    with open(js_path, "w") as js_file:
        js_file.write(rendered_template)
    
    return dash
    
def get_dash(name, skin, skindir):
           
    pydashfile = os.path.join(conf.dashboard_dir, "{}.pydash".format(name))
    dashfile = os.path.join(conf.dashboard_dir, "{}.dash".format(name))
    
    #
    # Grab CSS Variables
    #
    css_vars = load_css_params(skin, skindir)
    if css_vars == None:
        return None
    if os.path.isfile(pydashfile):
        with open(pydashfile, 'r') as dashfd:
            dash = ast.literal_eval(dashfd.read())
    elif os.path.isfile(dashfile):
        dash = load_dash(name, css_vars)
        if dash == None:
            return None
    else:
        ha.log(conf.logger, "WARNING", "Dashboard '{}' not found".format(name))
        return None
    
    if "head_includes" in css_vars and css_vars["head_includes"] != None:
        dash["head_includes"] = css_vars["head_includes"]
    else:
        dash["head_includes"] = []
    if "body_includes" in css_vars and css_vars["body_includes"] != None:
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
    
    try: 
        #
        # Base CSS template and compile
        #
        css_env = Environment(loader=FileSystemLoader(skindir))
        template = css_env.get_template("dashboard.css")
        rendered_css = template.render(css_vars)
        
        css = css + rendered_css + "\n"

        #
        # Template and compile widget CSS
        #
        for widget in dash["widgets"]:
            css_template = Environment(loader=BaseLoader).from_string(widgets[widget["parameters"]["widget_type"]]["css"])
            css_vars["id"] = widget["id"]
            rendered_css = css_template.render(css_vars)
            
            css = css + rendered_css + "\n"
         
        for widget in widgets:
            js = js + widgets[widget]["js"] + "\n"
            
    except KeyError:
        ha.log(conf.logger, "WARNING", "Widget type not found: {}".format(widget["parameters"]["widget_type"]))
        return None
    except:
        ha.log(conf.logger, "WARNING", '-' * 60)
        ha.log(conf.logger, "WARNING", "Unexpected error in CSS file")
        ha.log(conf.logger, "WARNING", '-' * 60)
        ha.log(conf.logger, "WARNING", traceback.format_exc())
        ha.log(conf.logger, "WARNING", '-' * 60)
        if rendered_css != None:
            ha.log(conf.logger, "WARNING", "Rendered CSS:")
            ha.log(conf.logger, "WARNING", rendered_css)
            ha.log(conf.logger, "WARNING", '-' * 60)
        return None
  

    if not os.path.exists(os.path.join(conf.compiled_css_dir, skin)):
        os.makedirs(os.path.join(conf.compiled_css_dir, skin))

    css_path = os.path.join(conf.compiled_css_dir, skin, "{}_application.css".format(name.lower()))
    with open(css_path, "w") as css_file:
        css_file.write(css)

    if not os.path.exists(conf.compiled_javascript_dir):
        os.makedirs(conf.compiled_javascript_dir) 
    
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
    widget_dir =  os.path.join(conf.dash_dir, "widgets")
    widget_dirs = os.listdir(path = widget_dir)
    widgets = {}
    for widget in widget_dirs:
        if os.path.isdir(os.path.join(widget_dir, widget)):
            jspath = os.path.join(widget_dir, widget, "{}.js".format(widget))
            csspath = os.path.join(widget_dir, widget, "{}.css".format(widget))
            htmlpath = os.path.join(widget_dir, widget, "{}.html".format(widget))
            with open (jspath, 'r') as fd:
                js = fd.read()
            with open (csspath, 'r') as fd:
                css = fd.read()
            with open (htmlpath, 'r') as fd:
                html = fd.read()
            widgets[widget] = {"js": js, "css": css, "html": html}
    return widgets
        