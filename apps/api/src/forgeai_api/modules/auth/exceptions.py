from forgeai_api.core.exceptions import ConflictError, UnauthorizedError


class EmailAlreadyRegisteredError(ConflictError):
    def __init__(self) -> None:
        super().__init__("An account with this email already exists.", error_type="email_taken")


class UsernameAlreadyTakenError(ConflictError):
    def __init__(self) -> None:
        super().__init__("This username is already taken.", error_type="username_taken")


class InvalidCredentialsError(UnauthorizedError):
    def __init__(self) -> None:
        # Deliberately identical whether the email doesn't exist or the password is
        # wrong — distinguishing the two lets an attacker enumerate registered emails.
        super().__init__("Incorrect email or password.", error_type="invalid_credentials")
