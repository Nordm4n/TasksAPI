class ApiSerializers:
    """
    Набор инструментов для преобразования данных
    """

    @staticmethod
    def serialize_task(task) -> dict:
        """
        Преобразует задачу из объекта в словарь с данными её полей
        :param task: Объект задачи
        :return: Словарь с данными задачи
        """
        return {'name': task.name,
                'description': task.description,
                'start_date': str(task.start_date),
                'stop_date': str(task.stop_date),
                'expired': str(task.expired),
                'task_id': str(task.task_id)}

    @staticmethod
    def items_str(data: dict) -> dict:
        """
        Преобразует все значения входящего словаря в строки
        :param data: Словарь с данными
        :return: Преобразованный словарь с данными
        """
        return {str(field): str(value) for field, value in data.items()}

    @staticmethod
    def items_attr(data: list | set, obj) -> dict:
        """
        На основе списка полей data получает одноимённые атрибуты у obj и формирует словарь
        :param data: Список полей
        :param obj: Объект
        :return: Словарь с данными объекта
        """
        return {field: getattr(obj, field) for field in data}

    def serialize_tasks(self, tasks: list) -> list[dict]:
        """
        Преобразует список из объектов задач в список словарей данными их полей
        :param tasks: Список объектов задач
        :return: Список словарей с данными
        """
        return [self.serialize_task(obj) for obj in tasks]
