# from decorators import debug, do_twice
import json
import time
import functools
import logging
import inspect
import datetime
import importlib
# import os
# import google

# from google.oauth2 import service_account
# from google.cloud import pubsub_v1

from django.conf import settings

from django.db import transaction

from .exceptions import MaxRetriesExceededError
from .queue_manager.google_pubsub import PubSubSystemUtils, get_default_queue_setting

from .models import TaskExecution
from .models import TaskExecutionResult
from .models import TaskExecutionTry


logger = logging.getLogger(__name__)

REGITERED_TASKS = dict()


class PubSubTaskUtils:
    def __init__(
        self,
        system_utils,  # 'utf-32',
        encoding="utf-8",  # 'utf-32',
    ):
        self.system_utils = system_utils
        self.encoding = encoding

    def serialize(self, args, kwargs, meta_info):
        serialized_data = json.dumps(
            {
                "args": args,
                "kwargs": kwargs,
                "meta_info": meta_info,
            }
        )
        binary_serialized_data = serialized_data.encode(
            encoding=self.encoding, errors="strict"
        )
        return binary_serialized_data

    def enqueue(self, serialized_data):
        pub_client = self.system_utils.get_publisher_client()
        topic_name = self.system_utils.get_topic_name()

        future = pub_client.publish(
            topic=topic_name,
            data=serialized_data,
            encoding=self.encoding,
            # pub_time=datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            pub_time=datetime.datetime.now(datetime.UTC).isoformat(),
            # **attrs: Union[bytes, str]
        )
        future.result()


class TaskTryObj:

    task_execution_db_instance = None
    task_execution_try_id = None
    task_execution_try_db_instance = None

    def __init__(
        self,
        task_execution_db_instance=None,
        task_execution_try_id=None,
        task_execution_try_db_instance=None,
        try_number=None,
    ) -> None:

        self.task_execution_db_instance = task_execution_db_instance

        if task_execution_try_db_instance:
            self.task_execution_try_db_instance = task_execution_try_db_instance
        elif task_execution_try_id:
            self.task_execution_try_db_instance = TaskExecutionTry.objects.get(
                id=task_execution_try_id,
                task_execution_id=self.task_execution_db_instance.id
            )
        elif try_number:
            task_execution_try = TaskExecutionTry(
                task_execution=self.task_execution_db_instance,
                try_number=try_number,
                # started_at='',
                # finished_at='',
            )
            task_execution_try.save()
            self.task_execution_try_db_instance = task_execution_try
        else:
            raise Exception("task_execution_try_id or task_execution_try_db_instance is required")


class TaskObj:

    func = None

    func_name = None
    module_name = None

    task_args = None
    task_kwargs = None

    # task_execution_db_instance = None
    # task_execution_try_db_instance = None

    def __init__(
        self,
        func=None,
        task_execution_id=None,
        task_execution_db_instance=None,
        # task_execution_try_id=None,
        # task_execution_try_db_instance=None,
        task_args=[],
        task_kwargs={},
        bind=False,
        max_retries=settings.I3TASKS.default_max_retries,
        encoding="utf-8",  # 'utf-32',
        pubsub_system_utils=None,
        pubsub_task_utils=None,
    ):

        self.bind = bind
        self.max_retries = max_retries

        self.encoding = encoding
        self.pubsub_system_utils = pubsub_system_utils
        self.pubsub_task_utils = pubsub_task_utils
        # self._func = func
        # self.func_name = self._func.__name__
        # self.module_name = inspect.getmodule(self._func).__name__

        if task_execution_id or task_execution_db_instance:
            self._get_task_db_instance(
                task_id=task_execution_id,
                task_db_instance=task_execution_db_instance,
                # task_args=task_args,
                # task_kwargs=task_kwargs,
            )
        elif func:
            self._create_task_db_instance(
                func=func,
                task_args=task_args,
                task_kwargs=task_kwargs,
            )
        else:
            raise Exception("func or task_id or task_db_instance is required")

    def __str__(self):
        return f"{self.module_name}.{self.func_name} (ID:{self.task_execution_db_instance.id})"

    def get_try_obj(self, task_execution_try_db_instance=None, task_execution_try_id=None, try_number=None):
        task_try_obj = TaskTryObj(
            task_execution_db_instance=self.task_execution_db_instance,
            task_execution_try_id=task_execution_try_id,
            task_execution_try_db_instance=task_execution_try_db_instance,
            try_number=try_number,
        )
        self.task_execution_try_db_instance = task_try_obj.task_execution_try_db_instance
        return task_try_obj

    def get_meta_info(self):
        self.meta_info = {
            "bind": self.bind,
            "encoding": self.pubsub_system_utils.encoding,
            "module_name": self.module_name,
            "func_name": self.func_name,
            "task_execution_id": self.task_execution_db_instance.id if self.task_execution_db_instance else None,
            "task_execution_try_id": self.task_execution_try_db_instance.id if self.task_execution_try_db_instance else None,
        }
        return self.meta_info

    def serialize(self, *args, **kwargs):
        return self.pubsub_task_utils.serialize(
            args=args, kwargs=kwargs, meta_info=self.get_meta_info()
        )

    def enqueue(self, *args, **kwargs):
        serialized_data = self.serialize(*args, **kwargs)
        self.pubsub_task_utils.enqueue(serialized_data)

    def import_task(self, func_name, module_name):
        task = None
        try:
            # equiv. of your `import matplotlib.text as text`
            task_module = importlib.import_module(module_name)
            task = getattr(task_module, func_name)
        except Exception as exc:
            logging.error(exc, exc_info=True)
            raise
        return task

    def __popolate_obj_from_db(self):
        self.task_args = self.task_execution_db_instance.task_args
        self.task_kwargs = self.task_execution_db_instance.task_kwargs
        self.func_name = self.task_execution_db_instance.task_name
        self.module_name = self.task_execution_db_instance.task_path
        func = self.import_task(
            func_name=self.func_name, module_name=self.module_name
        )
        if isinstance(func, TaskDecorator):
            self.func = func._func
        else:
            self.func = func

    def _create_task_db_instance(self,
            func,
            task_args=[],
            task_kwargs={}
        ):

        func_name = func.__name__
        module_name = inspect.getmodule(func).__name__

        self.task_execution_db_instance = TaskExecution(
            task_name=func_name,
            task_path=module_name,
            task_args=task_args,
            task_kwargs=task_kwargs,
        )
        self.task_execution_db_instance.save()
        self.__popolate_obj_from_db()

    def _get_task_db_instance(
        self,
        task_id=None,
        task_db_instance=None,
        # task_args=None,
        # task_kwargs=None,
    ):
        if task_db_instance:
            self.task_execution_db_instance = task_db_instance
            self.__popolate_obj_from_db()

        elif task_id:
            self.task_execution_db_instance = TaskExecution.objects.get(id=task_id)
            self.__popolate_obj_from_db()
        else:
            raise Exception("task_id or task_db_instance is required")

    def delay(self, *args, **kwargs):
        return self.async_run(*args, **kwargs)

    def _run(self, *args, **kwargs):
        # self.num_calls += 1
        # logger.info(f"Call {self.num_calls} of {self._func.__name__!r}")

        start_time = time.perf_counter()  # 1

        # import ipdb
        # ipdb.set_trace()

        mex = f"Starting {self.func_name} (ID:{self.task_execution_db_instance.id}) at {datetime.datetime.now(datetime.UTC).isoformat()}"
        logger.info(mex)

        mex_debug = f"func: {self.func}, module_name: {self.module_name}, func_name: {self.func_name}, Args: {args}, Kwargs: {kwargs}"
        logger.info(mex_debug)
        # logger.info("Something is happening before the function is called.")
        task_result = None
        if self.bind:
            task_result = self.func(*args, task_metadata=self, **kwargs)
        else:
            task_result = self.func(*args, **kwargs)
        # return func(*args, **kwargs)
        # logger.info("Something is happening after the function is called.")
        end_time = time.perf_counter()  # 2
        run_time = end_time - start_time  # 3

        mex = f"Finished {self.func_name} in {run_time:.4f} secs"
        logger.info(mex)

        mex = f"Finished {self.func_name} in {run_time:.4f} secs, result: {task_result}"
        logger.info(mex)


        return task_result

    def __call__(self, *args, **kwargs):
        return self.sync_run(*args, **kwargs)

    def async_run(self, *args, **kwargs):
        # binary_serialized_data = self.serialize(*args, **kwargs)
        # import ipdb
        # ipdb.set_trace()
        if settings.I3TASKS.force_sync:
            # self.serialize(*args, **kwargs)
            task_execution_try = self.sync_run(*args, **kwargs)
            return task_execution_try
        else:
            # meta_info = self.get_meta_info()
            # task_execution, task_execution_try = self._get_or_create_task_execution(
            #     meta_info=meta_info,
            #     _args=args,
            #     _kwargs=kwargs
            #     # *args,
            #     # **kwargs
            # )
            try_obj = self.get_try_obj(
                task_execution_try_db_instance=None,
                task_execution_try_id=None,
                try_number=1
            )
            task_execution_try = try_obj.task_execution_try_db_instance
            self.enqueue(*args, **kwargs)
            return task_execution_try
        # self._run(*args, **kwargs)

    def run_from_async(
            self,
            task_execution_try_db_instance=None,
            task_execution_try_id=None
        ):
        if not task_execution_try_db_instance and not task_execution_try_id:
            raise Exception("task_execution_try_db_instance or task_execution_try_id is required")
        try_obj = self.get_try_obj(
            task_execution_try_db_instance=task_execution_try_db_instance,
            task_execution_try_id=task_execution_try_id,
        )
        task_execution_try = try_obj.task_execution_try_db_instance

        try:
            task_execution_try_result = self._run_from_db(task_execution_try)

            if task_execution_try_result.is_success:
                return task_execution_try_result
        except Exception as e:
            logger.error(
                f"Error running task {self} -> {e}",
                # exc_info=True
            )
            if task_execution_try.try_number <= self.max_retries:
                try_obj = self.get_try_obj(
                    # task_execution_try_db_instance=task_execution_try_db_instance,
                    # task_execution_try_id=task_execution_try_id,
                    try_number=task_execution_try.try_number + 1
                )
                task_execution_try = try_obj.task_execution_try_db_instance
                self.enqueue(*self.task_args, **self.task_kwargs)
                logger.warning(f"TaskExecutionTry is not success, task: {self} retrying: {try_obj.task_execution_try_db_instance.try_number}")
                return task_execution_try
            else:
                raise MaxRetriesExceededError(f'Max Retries Exceeded: {self}')
            # raise Exception("TaskExecutionTry is not success")

    def sync_run(self, *args, **kwargs):
        # import ipdb
        # ipdb.set_trace()

        try_obj = self.get_try_obj(
            task_execution_try_db_instance=None,
            task_execution_try_id=None,
            try_number=1
        )
        task_execution_try = try_obj.task_execution_try_db_instance

        self.serialize(*args, **kwargs)

        return self._run_from_db(task_execution_try)

    def _run_from_db(self, task_execution_try):

        args = task_execution_try.task_execution.task_args
        kwargs = task_execution_try.task_execution.task_kwargs

        task_execution_try.started_at_at = datetime.datetime.now(datetime.UTC)
        task_execution_try.save()
        direct_result = None
        try:
            direct_result = self._run(*args, **kwargs)
            task_execution_try.is_success = True
            task_execution_try.is_completed = True
            task_execution_try.finished_at = datetime.datetime.now(datetime.UTC)
            task_execution_try.save()
        except Exception as e:
            task_execution_try.finished_at = datetime.datetime.now(datetime.UTC)
            task_execution_try.save()
            TaskExecutionResult(
                task_execution_try=task_execution_try,
                result=str(e),
            ).save()
            raise

        try:
            _res_json = json.dumps(direct_result)
        except Exception as e:
            logger.warning(f"Error serializing TaskExecutionResult: {e}")
            logger.exception(e, exc_info=True)
            TaskExecutionResult(
                task_execution_try=task_execution_try,
                result=str(direct_result),
            ).save()
            return task_execution_try

        try:
            if hasattr(task_execution_try, 'result'):
                logger.warning(f"TaskExecutionResult already exists: {task_execution_try.result}, {task_execution_try.result.result}")
                task_execution_try.result.result = _res_json
                task_execution_try.result.save()
            else:
                TaskExecutionResult(
                    task_execution_try=task_execution_try,
                    result=_res_json,
                ).save()
            return task_execution_try
        except Exception as e:
            # direct_result = self.sync_run(*args, **kwargs)
            logger.warning(f"Error saving TaskExecutionResult: {e}")
            logger.exception(e, exc_info=True)
            TaskExecutionResult(
                task_execution_try=task_execution_try,
                result=str(direct_result)
            ).save()
            return task_execution_try


class TaskDecorator:

    _func = None

    def __init__(
        self,
        func,
        bind=False,
        project_id=settings.PUBSUB_CONFIG.get("PROJECT_ID", None),
        topic_name=get_default_queue_setting("queue_name", "default"),
        subscription_name=get_default_queue_setting("subscription_name", "default"),
        encoding="utf-8",  # 'utf-32',
        max_retries=settings.I3TASKS.default_max_retries,
    ):
        functools.update_wrapper(self, func)
        self._func = func

        self.encoding = encoding
        self.pubsub_system_utils = PubSubSystemUtils(
            project_id=project_id,
            topic_name=topic_name,
            subscription_name=subscription_name,
            encoding=encoding,
        )
        self.pubsub_task_utils = PubSubTaskUtils(
            system_utils=self.pubsub_system_utils, encoding=encoding
        )

        self.bind = bind
        # https://docs.python.org/3/library/codecs.html#standard-encodings

        self.module_name = inspect.getmodule(self._func).__name__

        self.func_name = self._func.__name__

        self.max_retries = max_retries

        self.task_execution = None
        self.task_execution_try = None

    #     self.get_meta_info()

    # def get_meta_info(self):
    #     self.meta_info = {
    #         "bind": self.bind,
    #         "encoding": self.pubsub_system_utils.encoding,
    #         "module_name": self.module_name,
    #         "func_name": self.func_name,
    #         "task_execution_id": self.task_execution.id if self.task_execution else None,
    #         "task_execution_try_id": self.task_execution_try.id if self.task_execution_try else None,
    #     }
    #     return self.meta_info

    def delay(self, *args, **kwargs):
        return self.async_run(*args, **kwargs)

    def async_run(self, *args, **kwargs):
        task_obj = TaskObj(
            func=self._func,
            task_args=args,
            task_kwargs=kwargs,
            bind=self.bind,
            max_retries=self.max_retries,
            encoding=self.pubsub_system_utils.encoding,
            pubsub_system_utils=self.pubsub_system_utils,
            pubsub_task_utils=self.pubsub_task_utils,
        )
        return task_obj.async_run(*args, **kwargs)

    def sync_run(self, *args, meta_info=None, **kwargs):
        task_obj = TaskObj(
            func=self._func,
            task_args=args,
            task_kwargs=kwargs,
            bind=self.bind,
            max_retries=self.max_retries,
            encoding=self.pubsub_system_utils.encoding,
            pubsub_system_utils=self.pubsub_system_utils,
            pubsub_task_utils=self.pubsub_task_utils,
        )
        return task_obj.sync_run(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self.sync_run(*args, **kwargs)
