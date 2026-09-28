from django import template

register = template.Library()


@register.filter
def as_percentage(fraction):
    """Convert a 0-1 fraction (how overlap_percentage is stored) to a 0-100 percentage."""
    return fraction * 100
