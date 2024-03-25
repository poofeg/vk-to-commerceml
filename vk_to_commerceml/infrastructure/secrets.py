from cryptography.fernet import Fernet
from pydantic import SecretStr


class Secrets:
    def __init__(self, encryption_key: bytes) -> None:
        self.__fernet = Fernet(encryption_key)

    def encrypt(self, secret: SecretStr) -> str:
        return self.__fernet.encrypt(secret.get_secret_value().encode('utf-8')).decode('latin-1')

    def decrypt(self, token: str) -> SecretStr:
        return SecretStr(self.__fernet.decrypt(token.encode('latin-1')).decode('utf-8'))
