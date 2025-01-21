"""
Набор инструментов, связанных с логикой валидации и обработки пароля
"""
import os
from collections import namedtuple
from typing import Optional

import importlib.util

import Levenshtein
from api.config import PASSWORD_VALIDATORS, BASE_DIR, HASH_PASSWORD_ALGORITHM
from passlib.context import CryptContext
from password_strength import PasswordPolicy
from api.tools.validators import AbstractValidator


class LevenshteinPasswordValidator(AbstractValidator):
    """
    Валидатор, использующий расстояние Левенштейна для проверки схожести пароля с другими значениями модели User.
    Если схожесть между паролем и каким-либо из переданных значений превышает заданный коэффициент,
    то валидация считается неудачной, и выбрасывается исключение.
    """

    def _validate(self, **kwargs) -> None:
        """
        Выполняет проверку пароля на схожесть с другими значениями, используя алгоритм Левенштейна.
        Метод вычисляет коэффициент схожести между переданным паролем и значениями из других полей.
        Если схожесть между паролем и любым из значений превышает заданный коэффициент,
        выбрасывается исключение с указанием поля, с которым пароли слишком схожи.
        """
        password = kwargs.pop('password')
        coefficient = kwargs.get('coefficient', 0.7)
        other_fields = kwargs
        for field, value in other_fields.items():
            similarity = Levenshtein.ratio(password, value)
            if similarity > coefficient:
                raise ValueError(f"Значение пароля слишком похоже на значение {field}")


class StrengthPasswordValidator(AbstractValidator):
    """
    Валидатор сложности пароля. Проваливает валидацию
    """

    def _validate(self, **kwargs) -> None:
        password = kwargs.get('password')
        policy = PasswordPolicy.from_names(
            uppercase=kwargs.get('uppercase', 1), numbers=kwargs.get('numbers', 0), special=kwargs.get('special', 0)
        )
        if policy.test(password):
            raise ValueError("Введённый пароль слишком слабый!")


class PasswordValidatorController:
    """
    Контроллер для управления процессом валидации пароля с использованием нескольких валидаторов,
    заданных в конфигурации проекта. Класс предоставляет механизм для динамической загрузки валидаторов
    и их конфигурации из файла настроек, что позволяет легко расширять систему валидации.
    """

    @staticmethod
    def __get_validators() -> Optional[list[Optional[tuple]]]:
        """
        Собирает из переменной конфигурации список валидаторов пароля и конфигурации к ним.
        Валидация основана на словаре `PASSWORD_VALIDATORS`, где ключи — это строки с полными путями до
        классов валидаторов, а значения — это конфигурации для каждого валидатора.
        Этот метод динамически загружает указанные в конфигурации классы валидаторов, импортируя их из файлов по пути,
        указанному в конфигурации, и возвращает список кортежей из объектов валидаторов и их конфигураций.
        :return: Список кортежей, где каждый кортеж состоит из объекта валидатора и его конфигурации
                 (например, [('ValidatorClass', {'param': value})])
        """
        if not PASSWORD_VALIDATORS or not isinstance(PASSWORD_VALIDATORS, dict):
            return []
        validators = []
        for validator_str, params in PASSWORD_VALIDATORS.items():
            try:
                module_name, validator_class_name = validator_str.rsplit('.', 1)
                module_name = module_name.split('.')
                file_path = os.path.join(BASE_DIR, *module_name) + '.py'
                if not os.path.isfile(file_path):
                    raise FileNotFoundError(f"Не удалось найти файл: {file_path}")
                module_name = module_name[1]
                specification = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(specification)
                specification.loader.exec_module(module)
                if hasattr(module, validator_class_name):
                    Validator = namedtuple('Validator', 'obj config')
                    validators.append(Validator(obj=getattr(module, validator_class_name), config=params))
            except (FileNotFoundError, AttributeError, TypeError) as error:
                raise error
        return validators

    def validate(self, **kwargs) -> bool | str:
        """
        Собирает валидаторы, заданные в настройках проекта, и запускает валидацию пароля.
        В случае успеха возвращает True. В случае ошибки — строку с описанием ошибки.
        :param kwargs: Входные данные для валидаторов, например, пароль и дополнительные параметры для валидации.
        :return: Строка с ошибкой в случае неудачной валидации, или True в случае успешной валидации.
        """
        validators = self.__get_validators()
        try:
            # Для каждого валидатора из списка создаем экземпляр и запускаем валидацию
            [validator.obj(**{**validator.config, **kwargs}) for validator in validators]
        except Exception as error:
            return str(error)
        return True


class PasswordHashController:
    """
    Контроллер для работы с хешированием паролей. Обеспечивает создание хешей паролей с использованием
    алгоритма, указанного в конфигурации проекта, а также проверку пароля на соответствие хешу.
    """

    def __init__(self, schemes: str  = HASH_PASSWORD_ALGORITHM):
        self.crypt_context = CryptContext(schemes=schemes, deprecated="auto")

    def hash_password(self, password: str) -> str:
        """
        Хеширует пароль
        :param password: Пароль, который необходимо захешировать.
        :return: Хеш пароля в виде строки.
        """
        return self.crypt_context.hash(password)

    def check_password(self, password: str, hashed_password) -> bool:
        """
        Проверяет введённый пароль на соответствие с ранее сохранённым хешом пароля.
        :param password: Пароль, который нужно проверить.
        :param hashed_password: Хеш пароля, с которым необходимо сравнить.
        :return: `True`, если пароль соответствует хешу, иначе `False`.
        """
        return self.crypt_context.verify(password, hashed_password)