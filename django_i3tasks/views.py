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

from i3tasks.utils import TaskDecorator


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
            logger.info(f"json_body ==> {json_body}")
            logger.info(
                f'encoding ==> {json_body["message"]["attributes"]["encoding"]}'
            )
            logger.info(f'data ==> {json_body["message"]["data"]}')
            # decoded_data = str(
            #     object=json_body["message"]["data"],
            #     encoding=json_body["message"]["attributes"]["encoding"],
            #     errors="strict",
            # )
            decoded_data_base4 = base64.b64decode(json_body["message"]["data"])
            logger.info(f"data decoded base64 ==> {decoded_data_base4}")
            decoded_data = decoded_data_base4.decode(
                encoding=json_body["message"]["attributes"]["encoding"],
                errors="strict",
            )
            # logger.info(
            logger.info(f"data decoded ==> {decoded_data}")
            data = json.loads(decoded_data)
            logger.info(f"data ==> {data}")

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

    @csrf_exempt
    def post(self, request, *args, **kwargs):
        if not request.body:
            logger.error(f"missing post data")
            return JsonResponse({'status': 'bad', 'error': "missing post data"}, status=400)

        try:
            data = self.get_data(request_body=request.body)
        except Exception:
            logger.error(f"impossible to decode body")
            return JsonResponse({'status': 'bad', 'error': "impossible to decode body"}, status=400)

        if data is None:
            logger.error(f"None Data")
            return JsonResponse({'status': 'bad', 'error': "None Data"}, status=400)

        try:
            task = self.import_task(data["meta_info"])
        except Exception:
            logger.error(f"Not founded task {data['meta_info']}")
            return JsonResponse({'status': 'bad', 'error': "Not founded task"}, status=400)

        if task is None:
            logger.error(f"Not founded task is none {data['meta_info']}")
            return JsonResponse({'status': 'bad', 'error': "Not founded task"}, status=400)

        try:
            logger.error(f"Execution of {task} with args={data['args']} kwargs={data['kwargs']}")
            result = task.sync_run(*data["args"], **data["kwargs"])
        except Exception:
            logger.error(f"Error on task execution {task} args={data['args']} kwargs={data['kwargs']}")
            return JsonResponse({'status': 'bad', 'error': "Error on task execution"}, status=400)

        return JsonResponse({'status': 'ok', 'result': result}, status=200)


# @csrf_exempt
#     @require_POST
#     def pushed_tasks(request):
#         if not request.body:
#             return HttpResponse("missing post data", status=400)

#         data = None

#         try:
#             json_body = json.loads(request.body)
#             logger.info(f"json_body ==> {json_body}")
#             logger.info(f'encoding ==> {json_body["message"]["attributes"]["encoding"]}')
#             logger.info(f'data ==> {json_body["message"]["data"]}')
#             # decoded_data = str(
#             #     object=json_body["message"]["data"],
#             #     encoding=json_body["message"]["attributes"]["encoding"],
#             #     errors="strict",
#             # )
#             decoded_data_base4 = base64.b64decode(json_body["message"]["data"])
#             logger.info(f"data decoded base64 ==> {decoded_data_base4}")
#             decoded_data = decoded_data_base4.decode(
#                 encoding=json_body["message"]["attributes"]["encoding"],
#                 errors="strict",
#             )
#             # logger.info(
#             logger.info(f"data decoded ==> {decoded_data}")
#             data = json.loads(decoded_data)
#             logger.info(f"data ==> {data}")

#         except Exception as exc:
#             logger.error(exc)
#             return HttpResponse("impossible to decode body", status=400)

#         if data is None:
#             return HttpResponse("None Data", status=400)

#         task = None
#         try:
#             # equiv. of your `import matplotlib.text as text`
#             task_module = importlib.import_module(data["meta_info"]["module_name"])
#             task = getattr(task_module, data["meta_info"]["func_name"])
#         except Exception as exc:
#             logging.error(exc)

#         task.sync_run(*data["args"], **data["kwargs"])

#         return HttpResponse("asd", status=200)
