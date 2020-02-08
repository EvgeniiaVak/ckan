# -*- coding: utf-8 -*-

import pytest

from ckan.cli.cli import ckan


def test_without_args(cli):
    """Show help by default.
    """
    result = cli.invoke(ckan)
    assert result.output.startswith(u'Usage: ckan')
    assert not result.exit_code


def test_incorrect_config(cli):
    """Config file must exist.
    """
    result = cli.invoke(ckan, [u'-c', u'/a/b/c/d/e/f/g/h.ini'])
    assert result.output.startswith(u'Config file not found')


def test_correct_config(cli, ckan_config):
    """Presense of config file disables default printing of help message.
    """
    result = cli.invoke(ckan, [u'-c', ckan_config[u'__file__']])
    assert u'Error: Missing command.' in result.output
    assert result.exit_code


def test_correct_config_with_help(cli, ckan_config):
    """Config file not ignored when displaying usage.
    """
    result = cli.invoke(ckan, [u'-c', ckan_config[u'__file__'], u'-h'])
    assert not result.exit_code


def test_config_via_env_var(cli, ckan_config):
    """CliRunner uses test config automatically, so we have to explicitly
    set CLI `-c` option to `None` when using env `CKAN_INI`.

    """
    result = cli.invoke(ckan, [u'-c', None, u'-h'],
                        env={u'CKAN_INI': ckan_config[u'__file__']})
    assert not result.exit_code


def test_command_from_extension_is_not_available_without_extension(cli):
    """Extension must be enabled in order to make its commands available.
    """
    result = cli.invoke(ckan, [u'example-iclick-hello'])
    assert result.exit_code


@pytest.mark.ckan_config(u'ckan.plugins', u'example_iclick')
@pytest.mark.usefixtures(u'with_plugins')
def test_command_from_extension_is_not_available_without_additional_fixture(cli):
    """Without `with_extended_cli` extension still unable to register
    command durint tests.

    """
    result = cli.invoke(ckan, [u'example-iclick-hello'])
    assert result.exit_code


@pytest.mark.ckan_config(u'ckan.plugins', u'example_iclick')
@pytest.mark.usefixtures(u'with_plugins', u'with_extended_cli')
def test_command_from_extension_is_available_when_all_requirements_satisfied(cli):
    """When enabled, extension register its CLI commands.
    """
    result = cli.invoke(ckan, [u'example-iclick-hello'])
    assert not result.exit_code
