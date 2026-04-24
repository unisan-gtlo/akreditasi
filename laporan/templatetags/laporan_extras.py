"""Custom template tags untuk app laporan."""
from django import template

register = template.Library()


@register.filter(name='dictkey')
def dictkey(d, key):
    """Akses nested dict/object dengan key variable di template.
    
    Usage: {{ matrix|dictkey:standar_id|dictkey:prodi_code }}
    """
    if d is None:
        return None
    try:
        return d.get(key)
    except (AttributeError, TypeError):
        try:
            return d[key]
        except (KeyError, TypeError, IndexError):
            return None
