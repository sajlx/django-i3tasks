# from decorators import debug, do_twice
import json
import time
import functools
import logging
import inspect
import datetime
# import os
# import google

# from google.oauth2 import service_account
# from google.cloud import pubsub_v1

from django.conf import settings

from django_i3tasks.queue_manager.google_pubsub import PubSubSystemUtils, get_default_queue_setting


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
            pub_time=datetime.datetime.utcnow().isoformat(),
            # **attrs: Union[bytes, str]
        )
        future.result()


class TaskDecorator:
    def __init__(
        self,
        func,
        bind=False,
        project_id=settings.PUBSUB_CONFIG.get("PROJECT_ID", None),
        topic_name=get_default_queue_setting("queue_name", "default"),
        subscription_name=get_default_queue_setting("subscription_name", "default"),
        encoding="utf-8",  # 'utf-32',
    ):
        functools.update_wrapper(self, func)
        self._func = func

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

        self.get_meta_info()

    def __call__(self, *args, **kwargs):
        return self.sync_run(*args, **kwargs)
        # # self.num_calls += 1
        # # logger.info(f"Call {self.num_calls} of {self._func.__name__!r}")
        # start_time = time.perf_counter()    # 1
        # # logger.info("Something is happening before the function is called.")
        # task_result = self._func(*args, **kwargs)
        # # return func(*args, **kwargs)
        # # logger.info("Something is happening after the function is called.")
        # end_time = time.perf_counter()      # 2
        # run_time = end_time - start_time    # 3
        # logger.info(f"Finished {self._func.__name__!r} in {run_time:.4f} secs")
        # return task_result

    def get_meta_info(self):
        self.meta_info = {
            "bind": self.bind,
            "encoding": self.pubsub_system_utils.encoding,
            "module_name": self.module_name,
            "func_name": self.func_name,
        }
        return self.meta_info

    def serialize(self, *args, **kwargs):
        return self.pubsub_task_utils.serialize(
            args=args, kwargs=kwargs, meta_info=self.get_meta_info()
        )

    def enqueue(self, *args, **kwargs):
        serialized_data = self.serialize(*args, **kwargs)
        self.pubsub_task_utils.enqueue(serialized_data)
        # pub_client = self.get_publisher_client()
        # topic_name = self.get_topic_name()
        # binary_serialized_data = self.serialize(*args, **kwargs)
        # future = pub_client.publish(
        #     topic=topic_name,
        #     data=binary_serialized_data,
        #     encoding=self.encoding,
        #     # pub_time=datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        #     pub_time=datetime.datetime.utcnow().isoformat(),
        #     # **attrs: Union[bytes, str]
        # )
        # future.result()

    def async_run(self, *args, **kwargs):
        # binary_serialized_data = self.serialize(*args, **kwargs)
        self.enqueue(*args, **kwargs)

        # self._run(*args, **kwargs)

    def sync_run(self, *args, **kwargs):
        self.serialize(*args, **kwargs)
        return self._run(*args, **kwargs)

    def _run(self, *args, **kwargs):
        # self.num_calls += 1
        # logger.info(f"Call {self.num_calls} of {self._func.__name__!r}")
        start_time = time.perf_counter()  # 1
        # logger.info("Something is happening before the function is called.")
        task_result = None
        if self.bind:
            task_result = self._func(task_metadata=self, *args, **kwargs)
        else:
            task_result = self._func(*args, **kwargs)
        # return func(*args, **kwargs)
        # logger.info("Something is happening after the function is called.")
        end_time = time.perf_counter()  # 2
        run_time = end_time - start_time  # 3

        mex = f"Finished {self._func.__name__!r} in {run_time:.4f} secs"

        logger.info(mex)
        return task_result
