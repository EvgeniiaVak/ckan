# encoding: utf-8

import datetime
import logging
import os
import os.path
import tempfile

import pytest
from click.testing import CliRunner

import ckan.cli.cli as cli
import ckan.lib.jobs as jobs
import ckan.tests.helpers as helpers
from ckan.common import config

log = logging.getLogger(__name__)


def click(*args, **kwargs):
    """
    Call a click command.

    All arguments are parsed and passed on to the command. The
    ``--config`` option is automatically appended.

    By default, an ``AssertionError`` is raised if the command exits
    with a non-zero return code.
    Pass ``fail_on_error=False`` to disable this behavior.

    Example::

        code, output = click(u'jobs', u'list')
        assert u'My Job Title' in output

        code, output = click(u'jobs', u'foobar',
                                     fail_on_error=False)
        assert code == 1
        assert u'Unknown command' in output

    Any ``SystemExit`` raised by the command is swallowed.

    :returns: A tuple containing the return code, the content of
        output.
    """
    fail_on_error = kwargs.pop(u"fail_on_error", True)
    args = [u"--config=" + config[u"__file__"]] + list(args)
    runner = CliRunner()
    result = u''
    try:
        result = runner.invoke(cli.ckan, args)
        code = result.exit_code
    except SystemExit as e:
        code = e.code
    if code != 0 and fail_on_error:
        raise AssertionError(
            u"Paster command exited with non-zero return code {}: {}".format(
                code, result.output
            )
        )
    return code, result.output


@pytest.mark.usefixtures(u"clean_db")
class TestUserAdd(object):

    """Tests for UserCmd.add"""

    @classmethod
    def setup_class(cls):
        cls.user_cmd = cli.user
        cls.runner = CliRunner()

    def test_cli_user_add_valid_args(self):
        """Command shouldn't raise SystemExit when valid args are provided."""
        args = [
            u"berty",
            u"password=password123",
            u"fullname=Berty Guffball",
            u"email=berty@example.com",
        ]
        try:
            self.runner.invoke(self.user_cmd.add_user, args)
        except SystemExit:
            assert False, u"SystemExit exception shouldn't be raised"

    def test_cli_user_add_no_args(self):
        """Command with no args raises SystemExit."""
        self.user_cmd.args = [u"add"]
        result = self.runner.invoke(self.user_cmd.add_user)
        assert result.exception
        assert u"Missing argument" in result.output

    def test_cli_user_add_no_fullname(self):
        '''
        Command shouldn't raise SystemExit when fullname arg not present.
        '''
        args = [
            u"berty",
            u"password=password123",
            u"email=berty@example.com",
        ]
        try:
            self.runner.invoke(self.user_cmd.add_user, args)
        except SystemExit:
            assert False, u"SystemExit exception shouldn't be raised"

    def test_cli_user_add_unicode_fullname_unicode_decode_error(self):
        """
        Command shouldn't raise UnicodeDecodeError when fullname contains
        characters outside of the ascii characterset.
        """
        args = [
            u"berty",
            u"password=password123",
            u"fullname=Harold Müffintøp",
            u"email=berty@example.com",
        ]
        try:
            self.runner.invoke(self.user_cmd.add_user, args)
        except UnicodeDecodeError:
            assert False, u"UnicodeDecodeError exception shouldn't be raised"

    def test_cli_user_add_unicode_fullname_system_exit(self):
        """
        Command shouldn't raise SystemExit when fullname contains
        characters outside of the ascii characterset.
        """
        args = [
            u"berty",
            u"password=password123",
            u"fullname=Harold Müffintøp",
            u"email=berty@example.com",
        ]
        try:
            self.runner.invoke(self.user_cmd.add_user, args)
        except SystemExit:
            assert False, u"SystemExit exception shouldn't be raised"


class TestJobsUnknown(helpers.RQTestBase):
    """
    Test unknown sub-command for ``ckan jobs``.
    """

    def test_unknown_command(self):
        """
        Test error handling for unknown ``ckan jobs`` sub-command.
        """
        code, stdout = click(
            u"jobs", u"does-not-exist", fail_on_error=False
        )
        assert code != 0
        assert u"No such command" in stdout


class TestJobsList(helpers.RQTestBase):
    """
    Tests for ``ckan jobs list``.
    """

    def test_list_default_queue(self):
        """
        Test output of ``jobs list`` for default queue.
        """
        job = self.enqueue()
        stdout = click(u"jobs", u"list")[1]
        fields = stdout.split(u"\n")[-2].split()
        assert len(fields) == 3
        dt = datetime.datetime.strptime(fields[0], u"%Y-%m-%dT%H:%M:%S")
        now = datetime.datetime.utcnow()
        assert abs((now - dt).total_seconds()) < 10
        assert fields[1] == job.id
        assert fields[2] == jobs.DEFAULT_QUEUE_NAME

    def test_list_other_queue(self):
        """
        Test output of ``jobs.list`` for non-default queue.
        """
        job = self.enqueue(queue=u"my_queue")
        stdout = click(u"jobs", u"list")[1]
        fields = stdout.split(u"\n")[-2].split()
        assert len(fields) == 3
        assert fields[2] == u"my_queue"

    def test_list_title(self):
        """
        Test title output of ``jobs list``.
        """
        job = self.enqueue(title=u"My_Title")
        stdout = click(u"jobs", u"list")[1]
        fields = stdout.split(u"\n")[-2].split()
        assert len(fields) == 4
        assert fields[3] == u'"My_Title"'

    def test_list_filter(self):
        """
        Test filtering by queues for ``jobs list``.
        """
        job1 = self.enqueue(queue=u"q1")
        job2 = self.enqueue(queue=u"q2")
        job3 = self.enqueue(queue=u"q3")
        stdout = click(u"jobs", u"list", u"q1", u"q2")[1]
        assert u"q1" in stdout
        assert u"q2" in stdout
        assert u"q3" not in stdout


class TestJobShow(helpers.RQTestBase):
    """
    Tests for ``ckan jobs show``.
    """

    def test_show_existing(self):
        """
        Test ``jobs show`` for an existing job.
        """
        job = self.enqueue(queue=u"my_queue", title=u"My Title")
        output = click(u"jobs", u"show", job.id)[1]
        assert job.id in output
        assert jobs.remove_queue_name_prefix(job.origin) in output

    def test_show_missing_id(self):
        """
        Test ``jobs show`` with a missing ID.
        """
        code, output = click(u"jobs", u"show", fail_on_error=False)
        assert code != 0
        assert u'Error: Missing argument "id".' in output


class TestJobsCancel(helpers.RQTestBase):
    """
    Tests for ``ckan jobs cancel``.
    """

    def test_cancel_existing(self):
        """
        Test ``jobs cancel`` for an existing job.
        """
        job1 = self.enqueue()
        job2 = self.enqueue()
        stdout = click(u"jobs", u"cancel", job1.id)[1]
        all_jobs = self.all_jobs()
        assert len(all_jobs) == 1
        assert all_jobs[0].id == job2.id
        assert job1.id in stdout

    def test_cancel_not_existing(self):
        """
        Test ``jobs cancel`` for a not existing job.
        """
        code, output = click(
            u"jobs", u"cancel", u"does-not-exist", fail_on_error=False
        )
        # FIXME: after https://github.com/ckan/ckan/issues/5158
        # assert code != 0
        assert u"does-not-exist" in output

    def test_cancel_missing_id(self):
        """
        Test ``jobs cancel`` with a missing ID.
        """
        code, output = click(u"jobs", u"cancel", fail_on_error=False)
        assert code != 0
        assert u'Error: Missing argument "id".' in output


class TestJobsClear(helpers.RQTestBase):
    """
    Tests for ``ckan jobs clear``.
    """

    def test_clear_all_queues(self):
        """
        Test clearing all queues via ``jobs clear``.
        """
        self.enqueue()
        self.enqueue()
        self.enqueue(queue=u"q1")
        self.enqueue(queue=u"q2")
        stdout = click(u"jobs", u"clear")[1]
        assert jobs.DEFAULT_QUEUE_NAME in stdout
        assert u"q1" in stdout
        assert u"q2" in stdout
        assert self.all_jobs() == []

    def test_clear_specific_queues(self):
        """
        Test clearing specific queues via ``jobs clear``.
        """
        job1 = self.enqueue()
        job2 = self.enqueue(queue=u"q1")
        self.enqueue(queue=u"q2")
        self.enqueue(queue=u"q2")
        self.enqueue(queue=u"q3")
        stdout = click(u"jobs", u"clear", u"q2", u"q3")[1]
        assert u"q2" in stdout
        assert u"q3" in stdout
        assert jobs.DEFAULT_QUEUE_NAME not in stdout
        assert u"q1" not in stdout
        all_jobs = self.all_jobs()
        assert set(all_jobs) == {job1, job2}


class TestJobsTest(helpers.RQTestBase):
    """
    Tests for ``ckan jobs test``.
    """

    def test_test_default_queue(self):
        """
        Test ``jobs test`` for the default queue.
        """
        stdout = click(u"jobs", u"test")[1]
        all_jobs = self.all_jobs()
        assert len(all_jobs) == 1
        assert (
            jobs.remove_queue_name_prefix(all_jobs[0].origin)
            == jobs.DEFAULT_QUEUE_NAME
        )

    def test_test_specific_queues(self):
        """
        Test ``jobs test`` for specific queues.
        """
        stdout = click(u"jobs", u"test", u"q1", u"q2")[1]
        all_jobs = self.all_jobs()
        assert len(all_jobs) == 2
        assert {jobs.remove_queue_name_prefix(j.origin) for j in all_jobs} == {
            u"q1",
            u"q2",
        }


class TestJobsWorker(helpers.RQTestBase):
    """
    Tests for ``ckan jobs worker``.
    """

    # All tests of ``jobs worker`` must use the ``--burst`` option to
    # make sure that the worker exits.

    def test_worker_default_queue(self):
        """
        Test ``jobs worker`` with the default queue.
        """
        with tempfile.NamedTemporaryFile(delete=False) as f:
            self.enqueue(os.remove, args=[f.name])
            click(u"jobs", u"worker", u"--burst")
            all_jobs = self.all_jobs()
            assert all_jobs == []
            assert not (os.path.isfile(f.name))

    def test_worker_specific_queues(self):
        """
        Test ``jobs worker`` with specific queues.
        """
        with tempfile.NamedTemporaryFile(delete=False) as f:
            with tempfile.NamedTemporaryFile(delete=False) as g:
                job1 = self.enqueue()
                job2 = self.enqueue(queue=u"q2")
                self.enqueue(os.remove, args=[f.name], queue=u"q3")
                self.enqueue(os.remove, args=[g.name], queue=u"q4")
                click(u"jobs", u"worker", u"--burst", u"q3", u"q4")
                all_jobs = self.all_jobs()
                assert set(all_jobs) == {job1, job2}
                assert not (os.path.isfile(f.name))
                assert not (os.path.isfile(g.name))
