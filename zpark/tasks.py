import logging
import os

from celery import Celery
import celery.signals
from celery.utils.log import get_task_logger
from ciscosparkapi import SparkApiError

from zpark import app, basedir, spark_api
from zpark import celery as celery_app


logger = get_task_logger(__name__)


@celery_app.task(bind=True, default_retry_delay=20, max_retries=3)
def task_send_spark_message(self, to, text, md=None):
    # crude but good enough to tell the difference between roomId and
    # toPersonEmail inputs. this logic fails if we're passed a personId.
    if '@' in to:
        msg = dict(toPersonEmail=to)
    else:
        msg = dict(roomId=to)

    msg.update(text=text)

    if md is not None:
        msg.update(markdown=md)

    try:
        msg = spark_api.messages.create(**msg)

        logger.info("New Spark message created: toPersonEmail:{} "
                    "roomId:{} messageId:{}"
                        .format(msg.toPersonEmail, msg.roomId, msg.id))
        return msg.id
    except SparkApiError as e:
        msg = "The Spark API returned an error: {}".format(e)
        logger.error(msg)
        raise self.retry(exc=e)


@celery.signals.setup_logging.connect
def celery_setup_logging(loglevel=None, logfile=None, fmt=None,
                         colorize=None, **kwargs):
    import logging
    import logging.config
    import celery.app.log

    logconf = {
        'version': 1,
        'formatters': {
            'taskfmt': {
                '()': celery.app.log.TaskFormatter,
                'fmt': celery_app.conf.worker_task_log_format
            },
            'workerfmt': {
                'format': celery_app.conf.worker_log_format
            },
        },
        'handlers': {
            'taskh': {
                'level': loglevel or logging.INFO,
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(basedir, 'logs/task.log'),
                'maxBytes': app.config['APP_LOG_MAXBYTES'],
                'backupCount': app.config['APP_LOG_ROTATECOUNT'],
                'formatter': 'taskfmt'
            },
            'workh': {
                'level': loglevel or logging.INFO,
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(basedir, 'logs/task.log'),
                'maxBytes': app.config['APP_LOG_MAXBYTES'],
                'backupCount': app.config['APP_LOG_ROTATECOUNT'],
                'formatter': 'workerfmt'
            },
            'nullh': {
                'level': loglevel or logging.INFO,
                'class': 'logging.NullHandler',
            }
        },
        'loggers': {
            'celery': {
                'handlers': ['workh'],
                'level': loglevel or logging.INFO
            },
            'celery.task': {
                'handlers': ['taskh'],
                'level': loglevel or logging.INFO,
                'propagate': 0
            },
            # Celery will make this logger a child of 'celery.task' when
            # the get_task_logger(__name__) function is called at the top
            # of this module. Propagate logs upwards to 'celery.task' which
            # will emit the log message.
            __name__: {
                'handlers': ['nullh'],
                'level': loglevel or logging.INFO,
                'propagate': 1
            }
        },
    }

    logging.config.dictConfig(logconf)

