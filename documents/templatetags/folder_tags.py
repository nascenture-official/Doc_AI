from django import template

register = template.Library()


@register.inclusion_tag('documents/_folder_tree_node.html')
def render_folder_tree(folders, current_folder=None, level=0):
    """
    Recursively renders a folder tree level.
    Usage: {% render_folder_tree root_folders current_folder %}
    """
    return {
        'folders': folders,
        'current_folder': current_folder,
        'level': level,
    }
