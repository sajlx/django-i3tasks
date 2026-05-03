# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

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

from django.db.models import Count, Min, Q

from .models import TaskExecutionTry

from .utils import TaskDecorator, TaskObj


logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
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
        i3tasks_settings = getattr(settings, "I3TASKS", {})
        schedules = getattr(i3tasks_settings, "schedules", [])

        now = datetime.datetime.now(datetime.timezone.utc)

        # TODO:
        # force now from header or body value
        # put where to get in config
        # example: X-CloudScheduler-ScheduleTime
        # https://cloud.google.com/scheduler/docs/reference/rpc/google.cloud.scheduler.v1?_gl=1*1ydpxmp*_ga*MTk3ODIwNjg2My4xNzQ3MDU0ODI0*_ga_WH2QY8WWF5*czE3NDcyNDIzNzEkbzQkZzEkdDE3NDcyNDMyNzIkajU3JGwwJGgw#httptarget

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
                    cron,
                )
                if cron_is_matched:
                    logger.info(
                        "launching async task %s.%s at %s",
                        module_name,
                        func_name,
                        datetime.datetime.utcnow().isoformat(),
                    )
                    task = self.import_task(
                        meta_info={"module_name": module_name, "func_name": func_name}
                    )
                    task.async_run(*_args, **_kwargs)
                    # task_module = importlib.import_module(module_name)
                    # task = getattr(task_module, func_name)
                else:
                    iter = croniter(cron, now)
                    print(iter.get_next(datetime.datetime))

            except Exception as exc:
                logger.error(exc)

        return JsonResponse({"status": "ok"}, status=200)


@method_decorator(csrf_exempt, name="dispatch")
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
        return {"status": status, "result": result}

    def return_error_with_200(self, message):
        logger.error(f"{message}")
        return JsonResponse({"status": "bad", "error": message}, status=200)

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
            return self.return_error_with_200(
                f"Not founded task is none {data['meta_info']}"
            )

        # TODO: create import and rerun from db ids
        task_execution_try_id = None
        try:
            # task_execution_id
            task_execution_try_id = data.get("meta_info", {}).get(
                "task_execution_try_id", None
            )
        except Exception as exc:
            logger.error(f"Error on get task_execution_try_id")
            return self.return_error_with_200(
                f"Not task_execution_try_id in meta_info in data {data['meta_info']}"
            )
            # logger.error(exc, exc_info=True)

        # task_execution_try_id
        task_execution_try = None
        try:
            task_execution_try = TaskExecutionTry.objects.get(id=task_execution_try_id)
        except TaskExecutionTry.DoesNotExist:
            return self.return_error_with_200(
                f"TaskExecutionTry.DoesNotExist {task_execution_try_id}"
            )

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
            task_execution_try = task_obj.run_from_async(
                task_execution_try_id=task_execution_try_id
            )
            json_result = {
                # 'status': 'ok',
                "task_execution_id": task_execution_try.task_execution.id,
                "task_execution_try_id": task_execution_try.id,
                # 'task_execution_try_id': task_execution_try.id,
                "try_number": task_execution_try.try_number,
                "asked_at": task_execution_try.asked_at,
                "started_at": task_execution_try.started_at,
                "finished_at": task_execution_try.finished_at,
                "is_completed": task_execution_try.is_completed,
                "is_success": task_execution_try.is_success,
                "result": (
                    task_execution_try.result.result
                    if hasattr(task_execution_try, "result")
                    else None
                ),
            }
            return JsonResponse({"status": "ok", "result": json_result}, status=200)
        except Exception as exc:
            logger.error(
                f"Error on task execution {task_obj} args={task_obj.task_args} kwargs={task_obj.task_kwargs}"
            )
            logger.error(exc, exc_info=True)
            # logger.error(exc.with_traceback())
            return JsonResponse(
                {"status": "bad", "error": "Error on task execution"}, status=200
            )


@method_decorator(csrf_exempt, name="dispatch")
class HealthTaskView(View):
    """JSON health endpoint for external monitoring.

    GET /i3/tasks-health/  →  aggregates over TaskExecutionTry rows.
    Returns HTTP 200 for ok/warning, 503 for critical.
    """

    DEFAULT_WINDOW_MINUTES = 60
    DEFAULT_STUCK_MINUTES = 15
    DEFAULT_FAILED_THRESHOLD = 5
    DEFAULT_PENDING_AGE_THRESHOLD_S = 300

    def _get_setting(self, name, default):
        i3tasks_settings = getattr(settings, "I3TASKS", None)
        return getattr(i3tasks_settings, name, default) if i3tasks_settings else default

    def _check_token(self, request):
        expected = self._get_setting("health_token", None)
        if not expected:
            return True
        auth = request.headers.get("Authorization", "")
        provided = auth[7:] if auth.startswith("Bearer ") else request.GET.get("token", "")
        return provided == expected

    def get(self, request, *args, **kwargs):
        if not self._check_token(request):
            return JsonResponse({"status": "unauthorized"}, status=401)

        window_minutes = int(self._get_setting("health_window_minutes", self.DEFAULT_WINDOW_MINUTES))
        stuck_minutes = int(self._get_setting("health_stuck_minutes", self.DEFAULT_STUCK_MINUTES))
        failed_threshold = int(self._get_setting("health_failed_threshold", self.DEFAULT_FAILED_THRESHOLD))
        pending_age_threshold = int(self._get_setting(
            "health_pending_age_seconds_threshold", self.DEFAULT_PENDING_AGE_THRESHOLD_S
        ))

        now = datetime.datetime.now(datetime.timezone.utc)
        window_start = now - datetime.timedelta(minutes=window_minutes)
        stuck_cutoff = now - datetime.timedelta(minutes=stuck_minutes)

        tries_in_window = TaskExecutionTry.objects.filter(asked_at__gte=window_start)

        totals = tries_in_window.aggregate(
            pending=Count("id", filter=Q(started_at__isnull=True, is_completed=False)),
            running=Count("id", filter=Q(started_at__isnull=False, is_completed=False)),
            success=Count("id", filter=Q(is_completed=True, is_success=True)),
            failed=Count("id", filter=Q(is_completed=True, is_success=False)),
        )

        stuck_running = TaskExecutionTry.objects.filter(
            is_completed=False,
            started_at__isnull=False,
            started_at__lt=stuck_cutoff,
        ).count()

        oldest_pending = TaskExecutionTry.objects.filter(
            is_completed=False,
            started_at__isnull=True,
        ).aggregate(oldest=Min("asked_at"))["oldest"]
        oldest_pending_age = int((now - oldest_pending).total_seconds()) if oldest_pending else 0

        by_task_qs = (
            tries_in_window
            .values("task_execution__task_path", "task_execution__task_name")
            .annotate(
                success=Count("id", filter=Q(is_completed=True, is_success=True)),
                failed=Count("id", filter=Q(is_completed=True, is_success=False)),
                running=Count("id", filter=Q(started_at__isnull=False, is_completed=False)),
                pending=Count("id", filter=Q(started_at__isnull=True, is_completed=False)),
            )
            .order_by("-failed", "-success")[:50]
        )
        by_task = [
            {
                "task_path": row["task_execution__task_path"],
                "task_name": row["task_execution__task_name"],
                "success": row["success"],
                "failed": row["failed"],
                "running": row["running"],
                "pending": row["pending"],
            }
            for row in by_task_qs
        ]

        problems = []
        if stuck_running > 0:
            problems.append(
                f"{stuck_running} tries running for more than {stuck_minutes} minutes"
            )
        if oldest_pending_age > pending_age_threshold:
            problems.append(
                f"oldest pending try is {oldest_pending_age}s old (>{pending_age_threshold}s)"
            )
        if totals["failed"] > failed_threshold:
            problems.append(
                f"{totals['failed']} failed tries in last {window_minutes} minutes (>{failed_threshold})"
            )

        if stuck_running > 0 or oldest_pending_age > pending_age_threshold:
            status_label = "critical"
        elif problems:
            status_label = "warning"
        else:
            status_label = "ok"

        http_status = 503 if status_label == "critical" else 200

        return JsonResponse(
            {
                "status": status_label,
                "now": now.isoformat(),
                "window_minutes": window_minutes,
                "thresholds": {
                    "stuck_minutes": stuck_minutes,
                    "failed_threshold": failed_threshold,
                    "pending_age_seconds_threshold": pending_age_threshold,
                },
                "totals": totals,
                "stuck_running": stuck_running,
                "oldest_pending_age_seconds": oldest_pending_age,
                "problems": problems,
                "by_task": by_task,
            },
            status=http_status,
        )
