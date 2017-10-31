from collections import namedtuple
import json
from unittest.mock import PropertyMock, patch

from celery.exceptions import Retry
from ciscosparkapi import SparkApiError
from flask import url_for
from flask_testing import TestCase

import zpark


class BaseTestCase(TestCase):

    def create_app(self):
        zpark.app.config.update(
            DEBUG = False,
            TESTING = True,
            ZPARK_API_TOKEN = 'token12345'
        )
        return zpark.app

    def setUp(self):
        self.sb_api_token = ('Token', zpark.app.config['ZPARK_API_TOKEN'])
        zpark.app.logger.setLevel(999)

    def tearDown(self):
        pass


class ApiV1TestCase(BaseTestCase):

    def setUp(self):
        self.mock_sendmsg_patcher = \
                patch('zpark.tasks.task_send_spark_message.apply_async',
                      autospec=True)
        self.mock_sendmsg = self.mock_sendmsg_patcher.start()
        super(ApiV1TestCase, self).setUp()

    def tearDown(self):
        self.mock_sendmsg_patcher.stop()
        super(ApiV1TestCase, self).tearDown()

    ### GET /alert endpoint
    def test_alert_get_w_token(self):
        r = self.client.get(url_for('api_v1.alert'),
                            headers=[self.sb_api_token])

        self.assert_405(r)

    def test_alert_get_wo_token(self):
        r = self.client.get(url_for('api_v1.alert'))

        self.assert_405(r)

    ### POST /alert endpoint
    def test_alert_post_valid_alert_direct(self):
        to = u'joel@zpark.packetmischief'
        subject = u'This might ruin your day...'
        message = u'Your data center is on fire'

        type(self.mock_sendmsg.return_value).id = PropertyMock(
                                               return_value='id123abc')

        r = self.client.post(url_for('api_v1.alert'),
                             headers=[self.sb_api_token],
                             data=json.dumps({
                                'to': to,
                                'subject': subject,
                                'message': message
                             }),
                             content_type='application/json')
        self.assert_200(r)
        self.mock_sendmsg.assert_called_once()
        rjson = json.loads(r.data)
        self.assertEqual(rjson['message'], '{}\n\n{}'.format(subject, message))
        self.assertEqual(rjson['to'], to)
        self.assertEqual(rjson['taskid'], 'id123abc')

    def test_alert_post_valid_alert_group(self):
        to = u'roomid1234567'
        subject = u'This might ruin your day...'
        message = u'Your data center is on fire'

        type(self.mock_sendmsg.return_value).id = PropertyMock(
                                            return_value='id123abc')

        r = self.client.post(url_for('api_v1.alert'),
                             headers=[self.sb_api_token],
                             data=json.dumps({
                                'to': to,
                                'subject': subject,
                                'message': message
                             }),
                             content_type='application/json')
        self.assert_200(r)
        self.mock_sendmsg.assert_called_once()
        rjson = json.loads(r.data)
        self.assertEqual(rjson['message'], '{}\n\n{}'.format(subject, message))
        self.assertEqual(rjson['to'], to)
        self.assertEqual(rjson['taskid'], 'id123abc')

    def test_alert_post_valid_alert_wo_token(self):
        to = u'joel@zpark.packetmischief'
        subject = u'This might ruin your day...'
        message = u'Your data center is on fire'

        r = self.client.post(url_for('api_v1.alert'),
                             # no auth token here...
                             data=json.dumps({
                                'to': to,
                                'subject': subject,
                                'message': message
                             }),
                             content_type='application/json')
        self.assert_401(r)

    def _alert_post_missing_input(self, input_):
        r = self.client.post(url_for('api_v1.alert'),
                             headers=[self.sb_api_token],
                             data=json.dumps(input_),
                             content_type='application/json')
        self.assert_status(r, 400)
        self.assertIn(b'Required', r.data)

    def test_alert_post_missing_to(self):
        input_ = {
            # missing 'to'
            'subject': 'subj',
            'message': 'mess'
        }

        self._alert_post_missing_input(input_)

    def test_alert_post_missing_subject(self):
        input_ = {
            # missing 'subject'
            'to': 'joel',
            'message': 'mess'
        }

        self._alert_post_missing_input(input_)

    def test_alert_post_missing_message(self):
        """
        'message' is allowed to be absent so the result of this test should be
        an HTTP 200 and a good status message returned from the API.
        """
        input_ = {
            # missing 'message'
            'to': 'joel',
            'subject': 'subj',
        }

        type(self.mock_sendmsg.return_value).id = PropertyMock(
                                            return_value='id123abc')
        r = self.client.post(url_for('api_v1.alert'),
                             headers=[self.sb_api_token],
                             data=json.dumps(input_),
                             content_type='application/json')
        self.assert_200(r)
        rjson = json.loads(r.data)
        self.assertEqual(rjson['message'], input_['subject'])

    ### /ping endpoint
    def test_ping_get_wo_token(self):
        r = self.client.get(url_for('api_v1.ping'))

        self.assert_401(r)

    def test_ping_get_w_token(self):
        r = self.client.get(url_for('api_v1.ping'),
                            headers=[self.sb_api_token])

        self.assert_200(r)
        self.assertEqual(json.loads(r.data)['apiversion'], zpark.v1.API_VERSION)

    def test_ping_post_verb(self):
        r = self.client.post(url_for('api_v1.ping'))

        self.assert_405(r)


@patch('zpark.spark_api.messages.create', autospec=True)
class TaskTestCase(BaseTestCase):

    def test_task_send_spark_message(self, mock_sparkapi):
        to = u'joel@zpark.packetmischief'
        message = u'Your data center is on fire'

        my_spark_output_obj = namedtuple('sparkmsg',
                                      'toPersonEmail roomId text id created')
        # this is only a subset of the data returned by the API
        my_spark_output = my_spark_output_obj(
            created='2017-08-09T00:26:11.937Z',
            id='id123456',
            roomId=None,
            toPersonEmail=to,
            text=message
        )

        mock_sparkapi.return_value = my_spark_output

        self.assertEqual(my_spark_output.id,
                         zpark.tasks.task_send_spark_message(to, message))

    def test_task_send_spark_message_retry(self, mock_sparkapi):
        to = u'joel@zpark.packetmischief'
        message = u'Your data center is on fire'

        e = SparkApiError(429)

        mock_sparkapi.side_effect = [e, None]
        mock_retry = patch('zpark.tasks.task_send_spark_message.retry',
                           autospec=True)
        mock_retry_patcher = mock_retry.start()
        mock_retry_patcher.side_effect = Retry

        with self.assertRaises(Retry):
            zpark.tasks.task_send_spark_message(to, message).apply()

        mock_retry_patcher.assert_called_with(exc=e)

        mock_retry.stop()

