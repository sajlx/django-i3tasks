# from django.shortcuts import render

# Create your views here.
import json
import logging
import base64
import datetime
import importlib

from django.views.decorators.csrf import csrf_exempt

# from django.views.decorators.http import require_POST
from django.conf import settings

from croniter import croniter

from django.http import HttpResponse
from django.http import JsonResponse

from django.views import View

from django.utils.decorators import method_decorator

from .models import TaskExecutionTry

from .utils import TaskDecorator, TaskObj


logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class BeatTaskView(View):

    def import_task(self, meta_info: dict) -> TaskDecorator:
        task = None
        try:
            # equiv. of your `import matplotlib.text as text`
            task_module = importlib.import_module(meta_info["module_name"])
            task = getattr(task_module, meta_info["func_name"])
        except Exception as exc:
            logging.error(exc)
            raise
        return task

    @csrf_exempt
    def post(self, request, *args, **kwargs):
        # if not request.body:
        #     return HttpResponse("missing post data", status=400)

        # try:
        #     data = self.get_data(request_body=request.body)
        # except Exception:
        #     HttpResponse("impossible to decode body", status=400)

        # if data is None:
        #     return HttpResponse("None Data", status=400)
        i3tasks_settings = getattr(settings, 'I3TASKS', {})
        schedules = getattr(i3tasks_settings, 'schedules', [])

        now = datetime.datetime.utcnow()

        logger.info("test task matching cron at %s", now.isoformat())
        for schedule in schedules:
            try:
                module_name = schedule.module_name
                func_name = schedule.func_name
                _args = schedule.args
                _kwargs = schedule.kwargs

                cron = schedule.cron

                cron_is_matched = croniter.match(cron, now)
                logger.info(
                    "test task matching %s.%s at %s for %s",
                    module_name,
                    func_name,
                    now,
                    cron
                )
                if cron_is_matched:
                    logger.info(
                        "launching async task %s.%s at %s",
                        module_name,
                        func_name,
                        datetime.datetime.utcnow().isoformat()
                    )
                    task = self.import_task(meta_info={
                        'module_name': module_name,
                        'func_name': func_name
                    })
                    task.async_run(*_args, **_kwargs)
                    # task_module = importlib.import_module(module_name)
                    # task = getattr(task_module, func_name)
                else:
                    iter = croniter(cron, now)
                    print(iter.get_next(datetime))

            except Exception as exc:
                logger.error(exc)

        return JsonResponse({'status': 'ok'}, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class PushedTaskView(View):
    def get_data(self, request_body):
        data = None

        try:
            json_body = json.loads(request_body)
            logger.debug(f"json_body ==> {json_body}")
            logger.debug(
                f'encoding ==> {json_body["message"]["attributes"]["encoding"]}'
            )
            logger.debug(f'data ==> {json_body["message"]["data"]}')
            # decoded_data = str(
            #     object=json_body["message"]["data"],
            #     encoding=json_body["message"]["attributes"]["encoding"],
            #     errors="strict",
            # )
            decoded_data_base4 = base64.b64decode(json_body["message"]["data"])
            logger.debug(f"data decoded base64 ==> {decoded_data_base4}")
            decoded_data = decoded_data_base4.decode(
                encoding=json_body["message"]["attributes"]["encoding"],
                errors="strict",
            )
            # logger.debug(
            logger.debug(f"data decoded ==> {decoded_data}")
            data = json.loads(decoded_data)
            logger.debug(f"data ==> {data}")

        except Exception as exc:
            logger.error(exc)
            raise

        return data

    def import_task(self, meta_info):
        task = None
        try:
            # equiv. of your `import matplotlib.text as text`
            task_module = importlib.import_module(meta_info["module_name"])
            task = getattr(task_module, meta_info["func_name"])
        except Exception as exc:
            logging.error(exc)
            raise
        return task

    def format_json_response(self, status, result):
        return {'status': status, 'result': result}

    def return_error_with_200(self, message):
        logger.error(f"{message}")
        return JsonResponse({'status': 'bad', 'error': message}, status=200)

    @csrf_exempt
    def post(self, request, *args, **kwargs):
        if not request.body:
            return self.return_error_with_200(f"missing post data")

        try:
            data = self.get_data(request_body=request.body)
        except Exception:
            return self.return_error_with_200(f"impossible to decode body")

        if data is None:
            return self.return_error_with_200(f"None Data")

        if not data.get("meta_info", None):
            return self.return_error_with_200(f"Not meta_info in data {data}")

        logger.debug(f"Get meta_info {data['meta_info']}")

        try:
            task = self.import_task(data["meta_info"])
        except Exception:
            return self.return_error_with_200(f"Not founded task {data['meta_info']}")

        if task is None:
            return self.return_error_with_200(f"Not founded task is none {data['meta_info']}")

        # TODO: create import and rerun from db ids
        task_execution_try_id = None
        try:
            # task_execution_id
            task_execution_try_id = data.get('meta_info', {}).get("task_execution_try_id", None)
        except Exception as exc:
            logger.error(f"Error on get task_execution_try_id")
            return self.return_error_with_200(f"Not task_execution_try_id in meta_info in data {data['meta_info']}")
            # logger.error(exc, exc_info=True)

        # task_execution_try_id
        task_execution_try = None
        try:
            task_execution_try = TaskExecutionTry.objects.get(id=task_execution_try_id)
        except TaskExecutionTry.DoesNotExist:
            return self.return_error_with_200(f"TaskExecutionTry.DoesNotExist {task_execution_try_id}")

        task_obj = TaskObj(
            task_execution_id=task_execution_try.task_execution_id,
            encoding=task.encoding,
            max_retries=task.max_retries,
            pubsub_system_utils=task.pubsub_system_utils,
            pubsub_task_utils=task.pubsub_task_utils,
        )

        try:
            logger.info(
                f"Execution of {task_obj}, retry number: {task_execution_try.try_number} with args={task_obj.task_args} kwargs={task_obj.task_kwargs}"
            )
            task_execution_try = task_obj.run_from_async(task_execution_try_id=task_execution_try_id)
            json_result = {
                # 'status': 'ok',
                'task_execution_id': task_execution_try.task_execution.id,
                'task_execution_try_id': task_execution_try.id,
                # 'task_execution_try_id': task_execution_try.id,
                'try_number': task_execution_try.try_number,
                'asked_at': task_execution_try.asked_at,
                'started_at': task_execution_try.started_at,
                'finished_at': task_execution_try.finished_at,
                'is_completed': task_execution_try.is_completed,
                'is_success': task_execution_try.is_success,
                'result': task_execution_try.result.result if hasattr(task_execution_try, 'result') else None,
            }
            return JsonResponse({'status': 'ok', 'result': json_result}, status=200)
        except Exception as exc:
            logger.error(f"Error on task execution {task_obj} args={task_obj.task_args} kwargs={task_obj.task_kwargs}")
            logger.error(exc, exc_info=True)
            # logger.error(exc.with_traceback())
            return JsonResponse({'status': 'bad', 'error': "Error on task execution"}, status=200)
