from app.core.errors import NotFound


class LinkNotFound(NotFound):
    code = "link_not_found"
