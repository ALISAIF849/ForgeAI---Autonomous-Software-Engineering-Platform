from forgeai_api.core.exceptions import ConflictError, NotFoundError


class OrganizationSlugTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__("An organization with this slug already exists.", error_type="slug_taken")


class OrganizationNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("Organization not found.", error_type="organization_not_found")
