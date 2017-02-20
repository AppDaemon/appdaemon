import os
import ast
from scss.compiler import Compiler
import re
import yaml
import sys
import jinja2
from jinja2 import Environment, FileSystemLoader, select_autoescape

import appdaemon.homeassistant as ha
import appdaemon.conf as conf

def load_widget(includes, name):
    try:
        instantiated_widget = None
        for include in includes:
            if name in include:
                instantiated_widget = include[name]
                
        if instantiated_widget == None:
            yaml_path = os.path.join(conf.dashboard_dir, "{}.yaml".format(name))
            with open(yaml_path, 'r') as yamlfd:
                widget = yamlfd.read()
            instantiated_widget = yaml.load(widget)
    except FileNotFoundError:
        ha.log(conf.logger, "WARNING", "Unable to find widget definition for '{}'".format(name))
        # Return some valid data so the browser will render a blank widget
        return {"widget_type": "text"}
                
    try:
        widget_type = instantiated_widget["widget_type"]
        if os.path.isdir(os.path.join(conf.dash_dir, "widgets", widget_type)):
            # This is a base widget so return it in full
            return instantiated_widget
            
        # We are working with a derived widget so we need to do some merges and substitutions
        
        yaml_path = os.path.join(conf.dash_dir, "widgets", "{}.yaml".format(widget_type))
        
        yaml_file = ""
        templates = {}
        with open(yaml_path, 'r') as yamlfd:
            for line in yamlfd:            
                for ikey in instantiated_widget:
                    match = "{{{{{}}}}}".format(ikey)
                    if match in line:
                        templates[ikey] = 1
                        line = line.replace(match, instantiated_widget[ikey])
            
                yaml_file = yaml_file + line

        final_widget = yaml.load(yaml_file)
        
        for key in instantiated_widget:
            if key != "widget_type" and not key in templates:
                final_widget[key] = instantiated_widget[key]
                
        return final_widget
    except FileNotFoundError:
        ha.log(conf.logger, "WARNING", "Unable to find widget type '{}'".format(widget_type))
        # Return some valid data so the browser will render a blank widget
        return {"widget_type": "text"}
 
def add_layout(value, layout, occupied, dash, page, includes):
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
            widget = {}
            widget["id"] = "{}_{}".format(page, name)
            widget["position"] = [column, layout]
            widget["size"] = [xsize, ysize]
            widget["parameters"] = load_widget(includes, name)
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
 
def load_dash(name):
    dash, layout, occupied, includes = _load_dash(name, "dash", 0, {}, [], 1)
    return(dash)

def log_error(dash, name, error):
    dash["errors"].append("{}: {}".format(os.path.basename(name), error))
    ha.log(conf.logger, "WARNING", error)
    
def _load_dash(name, extension, layout, occupied, includes, level):

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
    page = "Default"

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
                    new_dash, layout, occupied, includes = _load_dash(os.path.join(conf.dashboard_dir, lay["include"]), "yaml", layout, occupied, includes, level + 1)
                    if new_dash != None:
                        merge_dashes(dash, new_dash)
                else:
                   log_error(dash, name, "Incorrect directive, should be 'include': {}".format(lay)) 
            else:
                layout = layout + 1
                add_layout(lay, layout, occupied, dash, page, includes)
                    
    return dash, layout, occupied, includes
    
def compile_dash(name, skin):

    if conf.dash_force_compile is False:
    
        compile = False
        
        for file in [
                     os.path.join(conf.compiled_css_dir, skin, "application.css"),
                     os.path.join(conf.compiled_javascript_dir, "application.js"),   
                     os.path.join(conf.compiled_javascript_dir, "{}_init.js".format(name.lower())),
                    ]:
            if not os.path.isfile(file):
                compile = True

        if compile is False:
            return {"errors": []}
    
    ha.log(conf.logger, "INFO", "Compiling dashboard '{}'".format(name))
    
    dash = get_dash(name, skin)
    if dash == None:
        dash_list = list_dashes()
        return {"dash_list": dash_list}
        
    params = dash
    params["stream_url"] = conf.stream_url
    params["base_url"] = conf.base_url
    params["name"] = name.lower()
    
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
    
def get_dash(name, skin):
           
    pydashfile = os.path.join(conf.dashboard_dir, "{}.pydash".format(name))
    dashfile = os.path.join(conf.dashboard_dir, "{}.dash".format(name))
    if os.path.isfile(pydashfile):
        with open(pydashfile, 'r') as dashfd:
            dash = ast.literal_eval(dashfd.read())

    elif os.path.isfile(dashfile):
        dash = load_dash(name)
        if dash == None:
            return None
    else:
        ha.log(conf.logger, "WARNING", "Dashboard '{}' not found".format(name))
        return None
    
    
    #
    # Load Widgets
    #
    widgets = get_widgets()
    
    #
    # Compile scss
    #
    scss = ""
    js = ""
    for widget in dash["widgets"]:
        scss = scss + widgets[widget["parameters"]["widget_type"]]["scss"] + "\n"
        js = js + widgets[widget["parameters"]["widget_type"]]["js"] + "\n"
        
    compiler = Compiler(search_path = [os.path.join(conf.css_dir, skin)])
    compiled_scss = compiler.compile_string(scss)
    
    if not os.path.exists(os.path.join(conf.compiled_css_dir, skin)):
        os.makedirs(os.path.join(conf.compiled_css_dir, skin))

    css_path = os.path.join(conf.compiled_css_dir, skin, "application.css")
    with open(css_path, "w") as css_file:
        css_file.write(compiled_scss)

    js_path = os.path.join(conf.compiled_javascript_dir, "application.js")
    with open(js_path, "w") as js_file:
        js_file.write(js)
    
    for widget in dash["widgets"]:
        html = widgets[widget["parameters"]["widget_type"]]["html"].replace('\n', '').replace('\r', '')
        widget["html"] = html

    return dash
    
def list_dashes():
    print(conf.dashboard_dir)
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
            csspath = os.path.join(widget_dir, widget, "{}.scss".format(widget))
            htmlpath = os.path.join(widget_dir, widget, "{}.html".format(widget))
            with open (jspath, 'r') as fd:
                js = fd.read()
            with open (csspath, 'r') as fd:
                scss = fd.read()
            with open (htmlpath, 'r') as fd:
                html = fd.read()
            widgets[widget] = {"js": js, "scss": scss, "html": html}
    return widgets
        