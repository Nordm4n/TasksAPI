import datetime
import logging
import random
import uuid
from time import sleep

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette import status
from starlette.responses import JSONResponse, Response

from api.config import DEFAULT_PATH, DEBUG
from api.db.manager import Manager, UserManager
from api.models.models import TaskRequiredInput, TaskInput, TaskCreate, BaseUser, UserRequest, UserDB, TaskDB, Base, \
    ReportCreate, ReportDB, ReportStatus, Session
from api.tools.api_tools import ApiSerializers


logger = logging.getLogger(__name__)
security = HTTPBasic()
app = FastAPI()
serializer_tool = ApiSerializers()


def authenticate(credentials: HTTPBasicCredentials = Depends(security)) -> Base:
    """
    Проверка аутентификации пользователя с использованием базовой аутентификации (HTTP Basic Authentication).
    Эта функция извлекает учетные данные (имя пользователя и пароль) из запроса, выполняет проверку
    с использованием метода `authenticate` менеджера пользователей (UserManager), и в случае успешной
    аутентификации возвращает объект пользователя. В случае неудачи выбрасывает ошибку HTTP 401.
    **Требования:**
    - Имя пользователя и пароль должны быть переданы через HTTP заголовок `Authorization` в формате Basic Auth.
    - Пароль должен быть правильно сопоставлен с сохраненным значением в базе данных.
    **Возвращаемое значение:**
    - Если аутентификация успешна, возвращается объект модели пользователя
    """
    username = credentials.username
    password = credentials.password
    user_manager = UserManager(Session())
    user = user_manager.authenticate(username, password)
    if not user:
        logger.warning(f"Неудачная попытка входа пользователем {username}. {datetime.datetime.now()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def get_manager():
    """
    :return: Объект подключения к db
    """
    db_manager = Manager(Session())
    try:
        yield db_manager
    except Exception as error:
        logger.critical(f'Проблемы во время работы с базой {error}')
    finally:
        db_manager.close()


# ------------------------------ Эндпоинты взаимодействия с задачами ---------------------------------------------------
@app.get(DEFAULT_PATH + 'tasks/{task_id}')
async def get_task(task_id: str, current_user=Depends(authenticate), manager=Depends(get_manager)):
    """
    Функция для возврата данных одной задачи
    :param task_id: Идентификатор задачи
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return: Данные в виде словаря о запрошенной задаче
    """
    try:
        task = manager.get(TaskDB, [
            TaskDB.task_id == uuid.UUID(task_id), TaskDB.user_id == current_user.user_id
        ])
        if not task:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        task = serializer_tool.serialize_task(task)
    except Exception as error:
        logger.error(
            f'Во время работы "get_task" произошла ошибка: {error}. Данные запроса {task_id}, {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(task, status_code=status.HTTP_200_OK)


@app.get(f'{DEFAULT_PATH}tasks/')
async def get_tasks(current_user=Depends(authenticate), manager=Depends(get_manager)):
    """
    Возвращает все задачи пользователя
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return: Словарь всех задач пользователя
    """
    try:
        tasks = manager.filter(TaskDB , [TaskDB.user_id == current_user.user_id])
        if not tasks:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        tasks = serializer_tool.serialize_tasks(tasks)
    except Exception as error:
        logger.error(
            f'Во время работы "get_tasks" произошла ошибка: {error}. Данные запроса: {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(tasks, status_code=status.HTTP_200_OK)


@app.delete(DEFAULT_PATH + 'tasks/{task_id}')
async def delete_tasks(task_id: str, current_user=Depends(authenticate), manager=Depends(get_manager)):
    """
    Функция для удаления задачи по её идентификатору
    :param task_id: Идентификатор задачи
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return: Ответ 204 в случае успеха удаления
    """
    try:
        manager.delete(TaskDB, uuid.UUID(task_id), TaskDB.task_id)
    except Exception as error:
        logger.error(
            f'Во время работы "delete_tasks" произошла ошибка: {error}. Данные запроса: {task_id} {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put(DEFAULT_PATH + 'tasks/{task_id}')
async def full_update_task(
        task_id: str, task: TaskRequiredInput, current_user=Depends(authenticate), manager=Depends(get_manager)
):
    """
    Функция для полноформатного обновления данных задачи. Поле expired будет занесено в базу на основе логики валидации
    :param task_id: Идентификатор задачи для обновления
    :param task: Данные задачи для обновления
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return:
    """
    try:
        db_task = manager.get(TaskDB, [
            TaskDB.task_id == uuid.UUID(task_id), TaskDB.user_id == current_user.user_id
        ])
        if not db_task:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        data = serializer_tool.items_attr(task.model_fields_set, task)
        manager.save(db_task, data)
    except Exception as error:
        logger.error(
            f'Во время работы "full_update_task" произошла ошибка: {error}. '
            f'Данные запроса: {task_id} {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(serializer_tool.items_str(data), status_code=status.HTTP_200_OK)


@app.patch(DEFAULT_PATH + 'tasks/{task_id}')
async def update_task(task_id: str, task: TaskInput, current_user=Depends(authenticate), manager=Depends(get_manager)):
    """
    Функция для частичного обновления данных задачи. Требует stop_date
    :param task_id: Идентификатор задачи для обновления
    :param task: Данные задачи для обновления
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return:
    """
    try:
        db_task = manager.get(TaskDB, [
            TaskDB.task_id == uuid.UUID(task_id), TaskDB.user_id == current_user.user_id
        ])
        if not db_task:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        data = serializer_tool.items_attr(task.model_fields_set, task) | {"user_id": current_user.user_id}
        manager.save(db_task, data)
    except Exception as error:
        logger.error(
            f'Во время работы "update_task" произошла ошибка: {error}. Данные запроса: {task_id} {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(serializer_tool.items_str(data), status_code=status.HTTP_200_OK)


@app.post(f"{DEFAULT_PATH}tasks/")
async def create_task(task: TaskCreate, current_user=Depends(authenticate), manager=Depends(get_manager)):
    """
    Функция для создания задачи
    :param task: Объект задачи с входными данными
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return: Словарь с данными о созданной задаче
    """
    try:
        data = serializer_tool.items_attr(task.model_fields_set, task) | {"user_id": current_user.user_id}
        task = manager.create(TaskDB, data)
        data = serializer_tool.items_str(data) | {'task_id' : str(task.task_id)}
    except Exception as error:
        logger.error(
            f'Во время работы "create_task" произошла ошибка: {error}. Данные запроса: {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(data, status_code=status.HTTP_201_CREATED)


# ------------------------------ Эндпоинты взаимодействия с пользователями ---------------------------------------------
@app.get(f'{DEFAULT_PATH}users/')
async def get_user(current_user=Depends(authenticate)):
    """
    Функция для получения данных пользователя
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :return: Словарь с данными пользователя
    """
    try:
        user_data = {
            field: str(value) for field, value in current_user.__dict__.items() if type(value) in [str, int, uuid.UUID]
        }
    except Exception as error:
        logger.error(
            f'Во время работы "get_user" произошла ошибка: {error}. Данные запроса: {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else None, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(user_data, status_code=status.HTTP_200_OK)


@app.put(f'{DEFAULT_PATH}users/')
async def update_user(user: BaseUser, current_user=Depends(authenticate), manager=Depends(get_manager)):
    """
    Функция для полноформатного обновления данных пользователя.
    :param user: Объект модели с данными пользователя
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return: Словарь с данными пользователя
    """
    try:
        data = serializer_tool.items_attr(user.model_fields_set, user)
        manager.update(UserDB, str(current_user.user_id), current_user.user_id, data)
    except Exception as error:
        logger.error(
            f'Во время работы "update_user" произошла ошибка: {error}. Данные запроса: {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else None, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(data, status_code=status.HTTP_200_OK)


@app.post(f'{DEFAULT_PATH}users/')
async def create_user(user: UserRequest, manager=Depends(get_manager)):
    """
    Функция для создания пользователя. Не требует авторизации
    :param user: Объект модели с данными нового пользователя
    :param manager: Объект подключения к db
    :return: Словарь с данными пользователя
    """
    try:
        data = serializer_tool.items_attr(user.model_fields_set, user)
        user = manager.create(UserDB, data)
        data.update({'pk': str(user.user_id)})
        del data['password']
    except Exception as error:
        logger.error(f'Во время работы "create_user" произошла ошибка: {error}.')
        return JSONResponse({'error': str(error)} if DEBUG else None, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(data, status_code=status.HTTP_201_CREATED)


# ------------------------------------ Асинхронное выполнение задач на "сервере" ---------------------------------------
def simulation_long_process(record_id: Base):
    """
    Симулирует выполнение длительной задачи. Ход выполнения отмечается в статусе объекта, над которым выполняется задача
    :param record_id: Идентификатор отчёта
    """
    manager = Manager(Session())
    record = manager.get(ReportDB, [ReportDB.report_id == record_id])
    try:
        data = {'status': record.status}
        if record:
            sleep(random.randint(2, 5))
            data['status'] = ReportStatus.RUNNING
            record = manager.save(record, data)
            sleep(random.randint(5, 10))
            failed_status_value = random.randint(0, 10)
            data['status'] = ReportStatus.COMPLETED
            if failed_status_value in [1, 3, 5]:
                data['status'] = ReportStatus.FAILED
            manager.save(record, data)
    except Exception as error:
        logger.error(f'Во время симуляции длительной задачи произошла неизвестная ошибка: {error}')
    finally:
        manager.close()

@app.post(f'{DEFAULT_PATH}reports/')
async def create_report(report: ReportCreate, background_tasks: BackgroundTasks, current_user=Depends(authenticate),
        manager=Depends(get_manager)):
    """
    Функция для получения данных для создания отчёта. Основные параметры - start_date и stop_date
    :param report: Данные для создания отчёта
    :param background_tasks: Менеджер фоновых задач для запуска обработки отчёта.
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
    :param manager: Объект подключения к db
    :return: Response 200 с id и статусом отчёта или Response 500 в случае ошибок
    """
    try:
        data = serializer_tool.items_attr(report.model_fields_set, report)
        data |= {'user_id': current_user.user_id, 'name': report.name}
        report = manager.create(ReportDB, data)
        background_tasks.add_task(simulation_long_process, report.report_id)
        data = serializer_tool.items_str({'report_id': report.report_id, 'status': report.status.value})
    except Exception as error:
        logger.error(f'Во время создания отчёта произошла неизвестная ошибка {error}')
        return JSONResponse({'error': str(error)} if DEBUG else None, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(data, status_code=status.HTTP_201_CREATED)


@app.get(f"{DEFAULT_PATH}reports/" + '{report_id}/')
async def check_report(report_id: uuid.UUID, current_user=Depends(authenticate), manager=Depends(get_manager)):
    """
    Функция для проверки состояние обработки задачи на "сервере"
    :param report_id: Идентификатор задачи для проверки
    :param current_user: Объект записи текущего аутентифицированного пользователя из DB
        :param manager: Объект подключения к db

    :return: Идентификатор задачи и её текущий статус
    """
    try:
        report = manager.get(ReportDB, [
            ReportDB.report_id == report_id, ReportDB.user_id == current_user.user_id
        ])
    except Exception as error:
        logger.error(f'Во время получения данных о задаче {report_id} произошла неизвестная ошибка {error}')
        return JSONResponse({'error': str(error)} if DEBUG else None, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(
        {"report_id": str(report.report_id), 'status': report.status.value}, status_code=status.HTTP_200_OK
    )


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)