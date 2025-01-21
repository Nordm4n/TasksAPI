"""
Изначально планировался небольшой модуль нескольких валидаторов. В итоге здесь остался абстрактный класс для
реализации валидаторов. Классы-наследники должны переопределить метод _validate для реализации своей логики валидации
Этот класс предоставляет базовую функциональность для выполнения валидации, а также управления исключениями,
которые могут возникать в процессе проверки.
"""
from abc import abstractmethod
from typing import Optional


class AbstractValidator:
    def __init__(self, **kwargs):
        """
        :param raise_exception: Статус, указывающий, выбрасывать исключение при провале валидации.
        """
        raise_exception = kwargs.get('raise_exception', True)
        if not isinstance(raise_exception, bool):
            raise_exception = True
        self.raise_exception = raise_exception
        self._run_validate(**kwargs)

    def _run_validate(self, **kwargs) -> Optional[bool]:
        """
        Обёртка для основного метода валидации, которая централизованно управляет логикой обработки ошибок
        и выбора действия в случае провала.
        При неудачной валидации метод либо выбрасывает исключение,
        либо возвращает False в зависимости от параметра raise_exception.
        :param kwargs: Атрибуты, необходимые для выполнения валидации в методах-потомках.
        :return: True, если валидация прошла успешно, или False, если выбрасывание исключения не настроено.
        """
        try:
            self._validate(**kwargs)
        except Exception as error:
            if self.raise_exception:
                raise error
            return False
        return True

    @abstractmethod
    def _validate(self, **kwargs) -> None:
        """
        Основной метод для реализации логики валидации, который должен быть переопределен в классе-наследнике.
        Этот метод выполняет собственную валидацию и выбрасывает исключение, если валидация не удалась.
        :param kwargs: Параметры для проверки валидации.
        :raises ValueError: Выбрасывается, если данные не проходят валидацию.
        :return: None
        """
