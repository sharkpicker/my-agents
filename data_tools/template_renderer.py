"""Jinja2 模板渲染器。"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


def render(template: str, **kwargs) -> str:
    """渲染模板,template 是模板名(不含 .html.j2 后缀)。"""
    tpl = env.get_template(f"{template}.html.j2")
    return tpl.render(**kwargs)