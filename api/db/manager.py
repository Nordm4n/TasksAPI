import logging
import uuid

from sqlalchemy.exc import SQLAlchemyError

from api.models.models import session, UserDB
from sqlalchemy.orm import Session, aliased
from api.tools.password_tools import PasswordHashController


logger = logging.getLogger(__name__)


class Manager:
    """
    Менеджер для запросов к базе
    """
    def __init__(self):
        self.session: Session = session  # сессия для работы с БД

    def _field_update(self, obj, data: dict):
        """
        Выполняет обновление полей объекта на основе полученных данных
        :param obj: Объект записи из db для обновления
        :param data: Данные для обновления
        :return: Обновленный объект
        """
        for field, value in data.items():
            if hasattr(obj, field):
                setattr(obj, field, value)
        self._execute_query(obj)
        return obj

    def _execute_query(self, obj):
        """
        Функция для непосредственного сохранения изменений объекта в базе
        :param obj: Объект для сохранения
        """
        try:
            self.session.commit()
            self.session.refresh(obj)
        except SQLAlchemyError as error:
            logger.critical(f"Во время запроса к DB произошла критическая ошибка: {error}")
            self.session.rollback()
            raise error

    def create(self, model_db, data: dict):
        """
        Создание новой записи в таблице.

        :param model_db: Модель базы данных
        :param data: Данные для создания записи
        :return: Созданный объект
        """
        instance = model_db(**data)
        self.session.add(instance)
        self._execute_query(instance)
        return instance

    def update(self, model_db, key: uuid.UUID | str, key_field, data: dict):
        """
        Обновление существующей записи в таблице.
        :param model_db: Модель базы данных
        :param key: UUID записи для обновления
        :param key_field: Объект ключевого поля у объекта записи
        :param data: Данные для обновления
        :return: Обновленный объект или None, если запись не найдена
        """
        if isinstance(key, str):
            try:
                key = uuid.UUID(key)
            except Exception as error:
                logger.error(f"Не удалось преобразовать ключ объекта {key} к UUID: {error}")
                return None
        instance = self.session.query(model_db).filter(key_field == key).first()
        if not instance:
            return None

        self._field_update(instance, data)
        return instance

    def save(self, obj, data):
        """
        Обновляет поля объекта на основе данных из data
        :param obj: Объект для обновления
        :param data: Данные для обновления
        :return:
        """
        return self._field_update(obj, data)

    def delete(self, model_db, key: uuid.UUID, key_field):
        """
        Удаление записи из базы данных.

        :param model_db: Модель базы данных
        :param key: UUID записи для удаления
        :param key_field: Объект ключевого поля у объекта записи
        :return: True, если запись удалена, иначе False
        """
        instance = self.session.query(model_db).filter(key_field == key).first()
        if not instance:
            return False
        self._execute_query(instance) # Применяем изменения в БД
        return True

    def all(self, model_db):
        """
        Получение всех записей для указанной модели.

        :param model_db: Модель базы данных
        :return: Список всех объектов модели
        """
        return self.session.query(model_db).all()

    def filter(self, model_db, filters: list = None):
        """
        Получение записей с применением условий фильтрации.

        :param model_db: Модель базы данных
        :param filters: Список условий для фильтрации, передается как список выражений (например, [model_db.column == value])
        :return: Отфильтрованные объекты модели
        """
        query = self.session.query(model_db)
        if filters:
            query = query.filter(*filters)  # Применяем все фильтры
        return query.all()


class UserManager(Manager):
    """
    Специальный менеджер для модели пользователя
    """
    user = UserDB
    def get_user(self, username: str) -> UserDB | None:
        """
        Получает запись пользователя из базы
        :param username: Логин пользователя
        :return: Объект записи пользователя или none
        """
        user = self.filter(self.user, [self.user.username == username])
        return user[0] if user else None

    def authenticate(self, username, password):
        """
        Функция аутентификации пользователя на основе его логина и пароля
        Сначала проверяется наличие пользователя с таким логином в базе. В случае наличия проверяется пароль
        :param username: Логин пользователя
        :param password: Незахешированный пароль пользователя
        :return: Запись пользователя из базы или False как сигнал, что аутентификация не пройдена
        """
        user = self.get_user(username)
        if user is None:
            return False
        controller  = PasswordHashController()
        authenticate = controller.check_password(password, user.password)
        return user if authenticate else False

