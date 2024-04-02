import logging

from .utils import TaskDecorator


logger = logging.getLogger(__name__)


@TaskDecorator
def test_task(*args, **kwargs):
    mex = f"This is the test task with args: {args} and kwargs: {kwargs}"
    logger.info(mex)
    return mex
