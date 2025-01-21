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
from api.models.models import TaskRequiredInput, TaskInput, TaskCreate, BaseUser, UserRequest, UserDB, TaskDB
from api.tools.api_tools import ApiSerializers


logger = logging.getLogger(__name__)
security = HTTPBasic()
app = FastAPI()
manager: Manager = Manager()
serializer_tool = ApiSerializers()


def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Проверка аутентификации пользователя с использованием базовой аутентификации (HTTP Basic Authentication).
    Эта функция извлекает учетные данные (имя пользователя и пароль) из запроса, выполняет проверку
    с использованием метода `authenticate` менеджера пользователей (UserManager), и в случае успешной
    аутентификации возвращает объект пользователя. В случае неудачи выбрасывает ошибку HTTP 401.
    **Требования:**
    - Имя пользователя и пароль должны быть переданы через HTTP заголовок `Authorization` в формате Basic Auth.
    - Пароль должен быть правильно сопоставлен с сохраненным значением в базе данных.
    **Возвращаемое значение:**
    - Если аутентификация успешна, возвращается объект пользователя
    """
    username = credentials.username
    password = credentials.password
    user_manager = UserManager()
    user = user_manager.authenticate(username, password)
    if not user:
        logger.warning(f"Попытка входа пользователем {username}. {datetime.datetime.now()}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


# ------------------------------ Эндпоинты взаимодействия с задачами ---------------------------------------------------
@app.get(DEFAULT_PATH + 'tasks/{task_id}')
async def get_task(task_id: str, current_user=Depends(authenticate)):
    """
    Функция для возврата данных одной задачи
    :param task_id: Идентификатор задачи
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
    :return: Данные в виде словаря о запрошенной задаче
    """
    try:
        task = manager.filter(TaskDB, [
            TaskDB.task_id == uuid.UUID(task_id), TaskDB.user_id == current_user.user_id
        ])
        if not task:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        task = serializer_tool.serialize_task(task[0])
    except Exception as error:
        logger.error(
            f'Во время работы "get_task" произошла ошибка: {error}. Данные запроса {task_id}, {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(task, status_code=status.HTTP_200_OK)


@app.get(f'{DEFAULT_PATH}tasks/')
async def get_tasks(current_user=Depends(authenticate)):
    """
    Возвращает все задачи пользователя
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
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
async def delete_tasks(task_id: str, current_user=Depends(authenticate)):
    """
    Функция для удаления задачи по её идентификатору
    :param task_id: Идентификатор задачи
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
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
async def full_update_task(task_id: str, task: TaskRequiredInput, current_user=Depends(authenticate)):
    """
    Функция для полноформатного обновления данных задачи. Поле expired будет занесено в базу на основе логики валидации
    :param task_id: Идентификатор задачи для обновления
    :param task: Данные задачи для обновления
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
    :return:
    """
    try:
        db_task = manager.filter(TaskDB, [
            TaskDB.task_id == uuid.UUID(task_id), TaskDB.user_id == current_user.user_id
        ])
        if not db_task:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        data = serializer_tool.items_attr(task.model_fields_set, task)
        task = db_task[0]
        manager.save(task, data)
    except Exception as error:
        logger.error(
            f'Во время работы "full_update_task" произошла ошибка: {error}. '
            f'Данные запроса: {task_id} {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(serializer_tool.items_str(data), status_code=status.HTTP_200_OK)


@app.patch(DEFAULT_PATH + 'tasks/{task_id}')
async def update_task(task_id: str, task: TaskInput, current_user=Depends(authenticate)):
    """
    Функция для частичного обновления данных задачи. Требует stop_date
    :param task_id: Идентификатор задачи для обновления
    :param task: Данные задачи для обновления
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
    :return:
    """
    try:
        db_task = manager.filter(TaskDB, [
            TaskDB.task_id == uuid.UUID(task_id), TaskDB.user_id == current_user.user_id
        ])
        if not db_task:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        data = serializer_tool.items_attr(task.model_fields_set, task) | {"user_id": current_user.user_id}
        task = db_task[0]
        manager.save(task, data)
    except Exception as error:
        logger.error(
            f'Во время работы "update_task" произошла ошибка: {error}. Данные запроса: {task_id} {current_user.user_id}'
        )
        return JSONResponse({'error': str(error)} if DEBUG else {}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(serializer_tool.items_str(data), status_code=status.HTTP_200_OK)


@app.post(f"{DEFAULT_PATH}tasks/")
async def create_task(task: TaskCreate, current_user=Depends(authenticate)):
    """
    Функция для создания задачи
    :param task: Объект задачи с входными данными
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
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
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
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
async def update_user(user: BaseUser, current_user=Depends(authenticate)):
    """
    Функция для полноформатного обновления данных пользователя.
    :param user: Объект модели с данными нового пользователя
    :param current_user: Авторизованный пользователь, от которого пришёл запрос
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
async def create_user(user: UserRequest):
    """
    Функция для создания пользователя. Не требует авторизации
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
"""
Реализовано всё не особо красиво, так как я не успевал сделать иначе.
"""


EXTRA = {}


def background_task(limit: int = 120):
    """
    функция, симулирующая бурную деятельность сервера
    :param limit: Верхняя граница времени выполнения задачи. По совместительству ключ для словаря
    :return:
    """
    minimum_limit = 30
    if limit < minimum_limit:
        limit, minimum_limit = minimum_limit, limit
    elif limit == minimum_limit:
        limit += 5
    EXTRA[limit] = 'Start'
    sleep(random.randint(minimum_limit, limit))
    EXTRA[limit] = 'Complete'
    sleep(600)
    EXTRA[limit] = 'To be removed'
    sleep(120)
    del EXTRA[limit]


@app.post(DEFAULT_PATH + 'async/{smth_value_id}')
async def async_simulator_create(smth_value_id: int, background_tasks: BackgroundTasks):
    """
    Запускает симуляцию выполнения тяжелой задачи на "сервере"
    :param smth_value_id: Верхняя граница времени на выполнение задачи
    :param background_tasks: Объект для корректной работы инициализации очереди задач
    :return: Словарь с полученным идентификатором
    """
    background_tasks.add_task(background_task, smth_value_id)
    return JSONResponse({"smth_value_id": smth_value_id})

@app.get(DEFAULT_PATH + 'async/{smth_value_id}/check/')
async def async_simulator(smth_value_id: int, background_tasks: BackgroundTasks):
    """
    Функция для проверки статуса задачи на основе полученного идентификатора задачи
    :param smth_value_id: Идентификатор задачи для проверки
    :param background_tasks: Объект для корректной работы инициализации очереди задач
    :return: Словарь с информацией о задаче
    """
    return JSONResponse({"smth_value_id": EXTRA.get(smth_value_id, "Для такого ключа не обнаружена задача")})



if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8000)