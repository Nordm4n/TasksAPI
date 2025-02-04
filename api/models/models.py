import enum
import inspect
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator, EmailStr

from sqlalchemy import Column, String, UUID, DATE, Boolean, ForeignKey, create_engine, Enum
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, validates

from api.tools.password_tools import PasswordValidatorController, PasswordHashController


def transform_date(date: str) -> datetime.date:
    """
    Преобразует полученный строковый формат полей даты к объекту date.
    Проверяет, не превышает ли дата начала дату окончания
    При фактическом завершении задачи позже установленного срока, автоматически устанавливает статус просрочки.
    :param date: Строка времени
    :return: Объект времени
    """
    try:
        return datetime.date(*[int(obj) for obj in date.split("-")])
    except ValueError:
        raise ValueError(f"Ошибка формата даты. Ожидается ГГГГ-ММ-ДД. Получено: {date}")


# ------------------------------------------------ Модели Pydantic -----------------------------------------------------
class BaseTask(BaseModel):
    """
    Базовая модель задач
    """
    name: str = Field(
        title='Название',
        description='Название задачи',
        min_length=4,
        max_length=64
    )
    description: str = Field(
        default=None,
        title='Описание',
        description='Описание задачи',
        max_length=512
    )
    start_date: datetime = Field(
        default_factory=datetime.today,
        title='Дата начала задачи',
        description='Дата начала задачи',
    )
    stop_date: datetime = Field(
        title='Дата окончания задачи',
        description='Дата окончания задачи'
    )
    finish_date: datetime = Field(
        default=None,
        title='Фактическая дата завершения',
        description='Фактическая дата завершения задачи',
    )
    expired: bool = Field(
        title='Статус несвоевременного выполнения задачи',
        description='Статус несвоевременного выполнения задачи',
        default=False
    )


class BaseRequiredTask(BaseTask):
    """
    Базовая модель задач со всеми обязательными для заполнения полями для HTTP - PUT
    """
    name: str = Field(
        title='Название',
        description='Название задачи',
        min_length=4,
        max_length=64
    )
    description: str = Field(
        title='Описание',
        description='Описание задачи',
        max_length=512
    )
    start_date: datetime = Field(
        title='Дата начала задачи',
        description='Дата начала задачи',
    )
    stop_date: datetime = Field(
        title='Дата окончания задачи',
        description='Дата окончания задачи'
    )
    finish_date: datetime = Field(
        title='Фактическая дата завершения',
        description='Фактическая дата завершения задачи',
    )
    expired: bool = Field(
        title='Статус несвоевременного выполнения задачи',
        description='Статус несвоевременного выполнения задачи',
    )


class TaskInput(BaseTask):
    """
    Модель для описания формата данных задачи, для получения данных и возврата данных в качестве ответа
    """
    @model_validator(mode='after')
    def date_fields_validator(self):
        """
        Преобразует полученные строковые значения временных полей в объекты даты.
        :return: Объект модели
        """
        if isinstance(self.stop_date, str):
            self.stop_date = transform_date(self.stop_date)
        if isinstance(self.start_date, str):
            self.start_date = transform_date(self.start_date)
        if self.stop_date < self.start_date:
            raise ValueError(f"stop_date '{self.stop_date}' не может быть меньше start_date '{self.start_date}'!")
        if self.finish_date and isinstance(self.finish_date, str):
            self.finish_date = transform_date(self.finish_date)
        if self.finish_date and self.finish_date > self.stop_date:
            self.expired = True
        return self

    class Config:
        extra = "forbid"


class TaskRequiredInput(BaseRequiredTask, TaskInput):
    """
    Модель данных для полного обновления объекта
    """

    class Config:
        extra = "forbid"


class TaskCreate(TaskInput):
    """
    Модель данных для валидации входных значений при создании записи
    """
    task_id: uuid.UUID = Field(default_factory=uuid.uuid4, title='Идентификатор', description='Идентификатор задачи')

    class Config:
        extra = "forbid"


class TaskRequest(TaskCreate):
    """
    Модель данных для создания записи в db
    """
    user_id: uuid.UUID = Field(title='Идентификатор пользователя', description='Идентификатор автора задачи')

    class Config:
        extra = "forbid"


class BaseUser(BaseModel):
    """
    Модель данных пользователя. Все поля по умолчанию обязательны к заполнению
    """
    username: str = Field(description='Логин пользователя', min_length=6, max_length=32)
    password: str = Field(description='Пароль пользователя', min_length=8, max_length=128)
    name: str = Field(description='Имя пользователя', min_length=2, max_length=32)
    email: EmailStr = Field(description='Почта пользователя')
    @model_validator(mode='after')
    def password_validator(self):
        password_validator = PasswordValidatorController()
        validate_result = password_validator.validate(
            password=self.password,
            **{'username': self.username, 'name': self.name, 'email': self.email}
        )
        if isinstance(validate_result, str):
            raise ValueError(validate_result)
        password_controller = PasswordHashController()
        self.password = password_controller.hash_password(self.password)
        return self

    class Config:
        extra = "forbid"

class UserRequest(BaseUser):
    """
    Модель данных для создания пользователя
    """
    user_id: uuid.UUID = Field(description='Идентификатор пользователя', default_factory=uuid.uuid4)
    tasks: list = Field(description='Связные задачи пользователя', default=None)

    class Config:
        extra = "forbid"


def generate_report_name() -> str:
    """
    Устанавливает name по умолчанию, если не получено значение от пользователя
    """
    return f'report_{datetime.now()}'


class ReportCreate(BaseModel):
    name: str = Field(
        default_factory=generate_report_name,
        description='Имя отчёта',
    )
    start_date: datetime = Field(
        title='Дата начала периода формирования отчёта',
        description='Дата начала периода формирования отчёта',
    )
    stop_date: datetime = Field(
        title='Дата окончания периода формирования отчёта',
        description='Дата окончания периода формирования отчёта',
    )

    @model_validator(mode='after')
    def date_fields_validator(self):
        """
        Преобразует полученные строковые значения временных полей в объекты даты.
        :return: Объект модели
        """
        if isinstance(self.stop_date, str):
            self.stop_date = transform_date(self.stop_date)
        if isinstance(self.start_date, str):
            self.start_date = transform_date(self.start_date)
        if self.stop_date < self.start_date:
            raise ValueError(f"stop_date '{self.stop_date}' не может быть меньше start_date '{self.start_date}'!")
        return self

    class Config:
        extra = "forbid"


# ------------------------------------------------ Модели SQL Alchemy и настройки к ним --------------------------------
Base = declarative_base()


class TaskDB(Base):
    __tablename__ = 'tasks'
    task_id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name: str = Column(String, nullable=True)
    description: str = Column(String, nullable=True)
    start_date: datetime.date = Column(DATE, nullable=False, default=datetime.today)
    stop_date: datetime.date = Column(DATE, nullable=False)
    finish_date: datetime.date = Column(DATE, nullable=True, default=None)
    expired: bool = Column(Boolean, default=False)
    user_id: uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    user = relationship("UserDB", back_populates='tasks')


class UserDB(Base):
    __tablename__ = 'users'
    user_id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    username: str = Column(String, unique=True, nullable=False, index=True)
    password: str = Column(String, nullable=False)
    name: str = Column(String, nullable=True)
    email: str = Column(String, nullable=True)
    tasks = relationship('TaskDB', back_populates='user')
    reports = relationship('ReportDB', back_populates='user')


class ReportStatus(enum.Enum):
    COMPLETED = 'Completed'
    FAILED = 'Failed' # Не используется
    RUNNING = 'Running'
    CREATED = 'Created'


class ReportDB(Base):
    __tablename__ = 'reports'
    report_id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    name: str = Column(String, nullable=False)
    start_date: datetime.date = Column(DATE, default=datetime.today, nullable=False)
    stop_date: datetime.date = Column(DATE, nullable=False)
    user_id: uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    user = relationship("UserDB", back_populates='reports')
    status = Column(Enum(ReportStatus), nullable=False, default=ReportStatus.CREATED)


engine = create_engine('sqlite:///db/api_tasks.db', connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)