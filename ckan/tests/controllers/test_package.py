# encoding: utf-8

from bs4 import BeautifulSoup
import mock

from ckan.lib.helpers import url_for
import pytest
import ckan.model as model
import ckan.model.activity as activity_model
import ckan.plugins as p
import ckan.lib.dictization as dictization
from ckan.logic.validators import object_id_validators, package_id_exists

import ckan.tests.helpers as helpers
import ckan.tests.factories as factories

webtest_submit = helpers.webtest_submit
submit_and_follow = helpers.submit_and_follow


def _get_package_new_page(app):
    user = factories.User()
    env = {"REMOTE_USER": user["name"].encode("ascii")}
    response = app.get(url=url_for("dataset.new"), extra_environ=env)
    return env, response


@pytest.mark.usefixtures("clean_db")
class TestPackageNew(object):
    def test_form_renders(self, app):
        env, response = _get_package_new_page(app)
        assert "dataset-edit" in response.forms

    @pytest.mark.ckan_config("ckan.auth.create_unowned_dataset", "false")
    def test_needs_organization_but_no_organizations_has_button(self, app):
        """ Scenario: The settings say every dataset needs an organization
        but there are no organizations. If the user is allowed to create an
        organization they should be prompted to do so when they try to create
        a new dataset"""
        sysadmin = factories.Sysadmin()

        env = {"REMOTE_USER": sysadmin["name"].encode("ascii")}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)
        assert "dataset-edit" not in response.forms
        assert url_for(controller="organization", action="new") in response

    @pytest.mark.ckan_config("ckan.auth.create_unowned_dataset", "false")
    @pytest.mark.ckan_config("ckan.auth.user_create_organizations", "false")
    @mock.patch("ckan.logic.auth.create.package_create")
    def test_needs_organization_but_no_organizations_no_button(
        self, mock_p_create, app
    ):
        """ Scenario: The settings say every dataset needs an organization
        but there are no organizations. If the user is not allowed to create an
        organization they should be told to ask the admin but no link should be
        presented. Note: This cannot happen with the default ckan and requires
        a plugin to overwrite the package_create behavior"""
        mock_p_create.return_value = {"success": True}

        user = factories.User()

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)

        assert "dataset-edit" not in response.forms
        assert url_for(controller="organization", action="new") not in response
        assert "Ask a system administrator" in response

    def test_name_required(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]

        response = webtest_submit(form, "save", status=200, extra_environ=env)
        assert "dataset-edit" in response.forms
        assert "Name: Missing value" in response

    def test_resource_form_renders(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"resource-form-renders"

        response = submit_and_follow(app, form, env, "save")
        assert "resource-edit" in response.forms

    def test_first_page_creates_draft_package(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"first-page-creates-draft"

        webtest_submit(form, "save", status=302, extra_environ=env)
        pkg = model.Package.by_name(u"first-page-creates-draft")
        assert pkg.state == "draft"

    def test_resource_required(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"one-resource-required"

        response = submit_and_follow(app, form, env, "save")
        form = response.forms["resource-edit"]

        response = webtest_submit(
            form, "save", value="go-metadata", status=200, extra_environ=env
        )
        assert "resource-edit" in response.forms
        assert "You must add at least one data resource" in response

    def test_complete_package_with_one_resource(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"complete-package-with-one-resource"

        response = submit_and_follow(app, form, env, "save")
        form = response.forms["resource-edit"]
        form["url"] = u"http://example.com/resource"

        submit_and_follow(app, form, env, "save", "go-metadata")
        pkg = model.Package.by_name(u"complete-package-with-one-resource")
        assert pkg.resources[0].url == u"http://example.com/resource"
        assert pkg.state == "active"

    def test_complete_package_with_two_resources(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"complete-package-with-two-resources"

        response = submit_and_follow(app, form, env, "save")
        form = response.forms["resource-edit"]
        form["url"] = u"http://example.com/resource0"

        response = submit_and_follow(app, form, env, "save", "again")
        form = response.forms["resource-edit"]
        form["url"] = u"http://example.com/resource1"

        submit_and_follow(app, form, env, "save", "go-metadata")
        pkg = model.Package.by_name(u"complete-package-with-two-resources")
        assert pkg.resources[0].url == u"http://example.com/resource0"
        assert pkg.resources[1].url == u"http://example.com/resource1"
        assert pkg.state == "active"

    def test_previous_button_works(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"previous-button-works"

        response = submit_and_follow(app, form, env, "save")
        form = response.forms["resource-edit"]

        response = submit_and_follow(app, form, env, "save", "go-dataset")
        assert "dataset-edit" in response.forms

    def test_previous_button_populates_form(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"previous-button-populates-form"

        response = submit_and_follow(app, form, env, "save")
        form = response.forms["resource-edit"]

        response = submit_and_follow(app, form, env, "save", "go-dataset")
        form = response.forms["dataset-edit"]
        assert "title" in form.fields
        assert form["name"].value == u"previous-button-populates-form"

    def test_previous_next_maintains_draft_state(self, app):
        env, response = _get_package_new_page(app)
        form = response.forms["dataset-edit"]
        form["name"] = u"previous-next-maintains-draft"

        response = submit_and_follow(app, form, env, "save")
        form = response.forms["resource-edit"]

        response = submit_and_follow(app, form, env, "save", "go-dataset")
        form = response.forms["dataset-edit"]

        webtest_submit(form, "save", status=302, extra_environ=env)
        pkg = model.Package.by_name(u"previous-next-maintains-draft")
        assert pkg.state == "draft"

    def test_dataset_edit_org_dropdown_visible_to_normal_user_with_orgs_available(
        self, app
    ):
        """
        The 'Organization' dropdown is available on the dataset create/edit
        page to normal (non-sysadmin) users who have organizations available
        to them.
        """
        user = factories.User()
        # user is admin of org.
        org = factories.Organization(
            name="my-org", users=[{"name": user["id"], "capacity": "admin"}]
        )

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)

        # organization dropdown available in create page.
        form = response.forms["dataset-edit"]
        assert "owner_org" in form.fields

        # create dataset
        form["name"] = u"my-dataset"
        form["owner_org"] = org["id"]
        response = submit_and_follow(app, form, env, "save")

        # add a resource to make the pkg active
        resource_form = response.forms["resource-edit"]
        resource_form["url"] = u"http://example.com/resource"
        submit_and_follow(app, resource_form, env, "save", "go-metadata")
        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"

        # edit package page response
        url = url_for("dataset.edit", id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        form = pkg_edit_response.forms["dataset-edit"]
        assert "owner_org" in form.fields
        # The organization id is in the response in a value attribute
        owner_org_options = [value for (value, _) in form["owner_org"].options]
        assert org["id"] in owner_org_options

    def test_dataset_edit_org_dropdown_normal_user_can_remove_org(self, app):
        """
        A normal user (non-sysadmin) can remove an organization from a dataset
        have permissions on.
        """
        user = factories.User()
        # user is admin of org.
        org = factories.Organization(
            name="my-org", users=[{"name": user["id"], "capacity": "admin"}]
        )

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)

        # create dataset with owner_org
        form = response.forms["dataset-edit"]
        form["name"] = u"my-dataset"
        form["owner_org"] = org["id"]
        response = submit_and_follow(app, form, env, "save")

        # add a resource to make the pkg active
        resource_form = response.forms["resource-edit"]
        resource_form["url"] = u"http://example.com/resource"
        submit_and_follow(app, resource_form, env, "save", "go-metadata")
        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"
        assert pkg.owner_org == org["id"]
        assert pkg.owner_org is not None

        # edit package page response
        url = url_for("dataset.edit", id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)

        # edit dataset
        edit_form = pkg_edit_response.forms["dataset-edit"]
        edit_form["owner_org"] = ""
        submit_and_follow(app, edit_form, env, "save")
        post_edit_pkg = model.Package.by_name(u"my-dataset")
        assert post_edit_pkg.owner_org is None
        assert post_edit_pkg.owner_org != org["id"]

    def test_dataset_edit_org_dropdown_not_visible_to_normal_user_with_no_orgs_available(
        self, app
    ):
        """
        The 'Organization' dropdown is not available on the dataset
        create/edit page to normal (non-sysadmin) users who have no
        organizations available to them.
        """
        user = factories.User()
        # user isn't admin of org.
        org = factories.Organization(name="my-org")

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)

        # organization dropdown not in create page.
        form = response.forms["dataset-edit"]
        assert "owner_org" not in form.fields

        # create dataset
        form["name"] = u"my-dataset"
        response = submit_and_follow(app, form, env, "save")

        # add a resource to make the pkg active
        resource_form = response.forms["resource-edit"]
        resource_form["url"] = u"http://example.com/resource"
        submit_and_follow(app, resource_form, env, "save", "go-metadata")
        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"

        # edit package response
        url = url_for(
            "dataset.edit", id=model.Package.by_name(u"my-dataset").id
        )
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        form = pkg_edit_response.forms["dataset-edit"]
        assert "owner_org" not in form.fields
        # The organization id is in the response in a value attribute
        assert 'value="{0}"'.format(org["id"]) not in pkg_edit_response

    def test_dataset_edit_org_dropdown_visible_to_sysadmin_with_no_orgs_available(
        self, app
    ):
        """
        The 'Organization' dropdown is available to sysadmin users regardless
        of whether they personally have an organization they administrate.
        """
        user = factories.User()
        sysadmin = factories.Sysadmin()
        # user is admin of org.
        org = factories.Organization(
            name="my-org", users=[{"name": user["id"], "capacity": "admin"}]
        )

        # user in env is sysadmin
        env = {"REMOTE_USER": sysadmin["name"].encode("ascii")}
        response = app.get(url=url_for("dataset.new"), extra_environ=env)

        # organization dropdown available in create page.
        assert 'id="field-organizations"' in response

        # create dataset
        form = response.forms["dataset-edit"]
        form["name"] = u"my-dataset"
        form["owner_org"] = org["id"]
        response = submit_and_follow(app, form, env, "save")

        # add a resource to make the pkg active
        resource_form = response.forms["resource-edit"]
        resource_form["url"] = u"http://example.com/resource"
        submit_and_follow(app, resource_form, env, "save", "go-metadata")
        pkg = model.Package.by_name(u"my-dataset")
        assert pkg.state == "active"

        # edit package page response
        url = url_for("dataset.edit", id=pkg.id)
        pkg_edit_response = app.get(url=url, extra_environ=env)
        # A field with the correct id is in the response
        assert 'id="field-organizations"' in pkg_edit_response
        # The organization id is in the response in a value attribute
        assert 'value="{0}"'.format(org["id"]) in pkg_edit_response

    def test_unauthed_user_creating_dataset(self, app):

        # provide REMOTE_ADDR to idenfity as remote user, see
        # ckan.views.identify_user() for details
        response = app.post(
            url=url_for("dataset.new"),
            extra_environ={"REMOTE_ADDR": "127.0.0.1"},
            status=403,
        )


@pytest.mark.usefixtures("clean_db")
class TestPackageEdit(object):
    def test_organization_admin_can_edit(self, app):
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env
        )
        form = response.forms["dataset-edit"]
        form["notes"] = u"edited description"
        submit_and_follow(app, form, env, "save")

        result = helpers.call_action("package_show", id=dataset["id"])
        assert u"edited description" == result["notes"]

    def test_organization_editor_can_edit(self, app):
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "editor"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env
        )
        form = response.forms["dataset-edit"]
        form["notes"] = u"edited description"
        submit_and_follow(app, form, env, "save")

        result = helpers.call_action("package_show", id=dataset["id"])
        assert u"edited description" == result["notes"]

    def test_organization_member_cannot_edit(self, app):
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]),
            extra_environ=env,
            status=403,
        )

    def test_user_not_in_organization_cannot_edit(self, app):
        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]),
            extra_environ=env,
            status=403,
        )

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.post(
            url_for("dataset.edit", id=dataset["name"]),
            {"notes": "edited description"},
            extra_environ=env,
            status=403,
        )

    def test_anonymous_user_cannot_edit(self, app):
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"])
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), status=403
        )

        response = app.post(
            url_for("dataset.edit", id=dataset["name"]),
            {"notes": "edited description"},
            status=403,
        )

    def test_validation_errors_for_dataset_name_appear(self, app):
        """fill out a bad dataset set name and make sure errors appear"""
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.edit", id=dataset["name"]), extra_environ=env
        )
        form = response.forms["dataset-edit"]
        form["name"] = u"this is not a valid name"
        response = webtest_submit(form, "save", status=200, extra_environ=env)
        assert "The form contains invalid entries" in response.body

        assert (
            "Name: Must be purely lowercase alphanumeric (ascii) "
            "characters and these symbols: -_" in response.body
        )

    def test_edit_a_dataset_that_does_not_exist_404s(self, app):
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.edit", id="does-not-exist"),
            extra_environ=env,
            expect_errors=True,
        )
        assert 404 == response.status_int


@pytest.mark.usefixtures("clean_db")
class TestPackageRead(object):
    def test_read(self, app):
        dataset = factories.Dataset()
        response = app.get(url_for("dataset.read", id=dataset["name"]))
        response.mustcontain("Test Dataset")
        response.mustcontain("Just another test dataset")

    def test_organization_members_can_read_private_datasets(self, app):
        members = {
            "member": factories.User(),
            "editor": factories.User(),
            "admin": factories.User(),
            "sysadmin": factories.Sysadmin(),
        }
        organization = factories.Organization(
            users=[
                {"name": members["member"]["id"], "capacity": "member"},
                {"name": members["editor"]["id"], "capacity": "editor"},
                {"name": members["admin"]["id"], "capacity": "admin"},
            ]
        )
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        for user, user_dict in members.items():
            response = app.get(
                url_for("dataset.read", id=dataset["name"]),
                extra_environ={
                    "REMOTE_USER": user_dict["name"].encode("ascii")
                },
            )
            assert "Test Dataset" in response.body
            assert "Just another test dataset" in response.body

    def test_anonymous_users_cannot_read_private_datasets(self, app):
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        response = app.get(
            url_for("dataset.read", id=dataset["name"]), status=404
        )
        assert 404 == response.status_int

    def test_user_not_in_organization_cannot_read_private_datasets(self, app):
        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        response = app.get(
            url_for("dataset.read", id=dataset["name"]),
            extra_environ={"REMOTE_USER": user["name"].encode("ascii")},
            status=404,
        )
        assert 404 == response.status_int

    def test_read_rdf(self, app):
        """ The RDF outputs now live in ckanext-dcat"""
        dataset1 = factories.Dataset()

        offset = url_for("dataset.read", id=dataset1["name"]) + ".rdf"
        app.get(offset, status=404)

    def test_read_n3(self, app):
        """ The RDF outputs now live in ckanext-dcat"""
        dataset1 = factories.Dataset()

        offset = url_for("dataset.read", id=dataset1["name"]) + ".n3"
        app.get(offset, status=404)

    def test_read_dataset_as_it_used_to_be(self, app):
        dataset = factories.Dataset(title="Original title")
        activity = (
            model.Session.query(model.Activity)
            .filter_by(object_id=dataset["id"])
            .one()
        )
        dataset["title"] = "Changed title"
        helpers.call_action("package_update", **dataset)

        sysadmin = factories.Sysadmin()
        env = {"REMOTE_USER": sysadmin["name"].encode("ascii")}
        response = app.get(
            url_for(
                "dataset.read", id=dataset["name"], activity_id=activity.id
            ),
            extra_environ=env,
        )
        response.mustcontain("Original title")

    def test_read_dataset_as_it_used_to_be_but_is_unmigrated(self, app):
        # Renders the dataset using the activity detail, when that Activity was
        # created with an earlier version of CKAN, and it has not been migrated
        # (with migrate_package_activity.py), which should give a 404

        user = factories.User()
        dataset = factories.Dataset(user=user)

        # delete the modern Activity object that's been automatically created
        modern_activity = (
            model.Session.query(model.Activity)
            .filter_by(object_id=dataset["id"])
            .one()
        )
        modern_activity.delete()

        # Create an Activity object as it was in earlier versions of CKAN.
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L508
        activity_type = "changed"
        dataset_table_dict = dictization.table_dictize(
            model.Package.get(dataset["id"]), context={"model": model}
        )
        activity = model.Activity(
            user_id=user["id"],
            object_id=dataset["id"],
            activity_type="%s package" % activity_type,
            data={
                # "actor": a legacy activity had no "actor"
                # "package": a legacy activity had just the package table,
                # rather than the result of package_show
                "package": dataset_table_dict
            },
        )
        model.Session.add(activity)
        # a legacy activity had a ActivityDetail associated with the Activity
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L542
        activity_detail = model.ActivityDetail(
            activity_id=activity.id,
            object_id=dataset["id"],
            object_type=u"Package",
            activity_type=activity_type,
            data={u"package": dataset_table_dict},
        )
        model.Session.add(activity_detail)
        model.Session.flush()

        sysadmin = factories.Sysadmin()
        env = {"REMOTE_USER": sysadmin["name"].encode("ascii")}
        response = app.get(
            url_for(
                "dataset.read", id=dataset["name"], activity_id=activity.id
            ),
            extra_environ=env,
            status=404,
        )


@pytest.mark.usefixtures("clean_db")
class TestPackageDelete(object):
    def test_owner_delete(self, app):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.post(
            url_for("dataset.delete", id=dataset["name"]), extra_environ=env
        )
        response = response.follow()
        assert 200 == response.status_int

        deleted = helpers.call_action("package_show", id=dataset["id"])
        assert "deleted" == deleted["state"]

    def test_delete_on_non_existing_dataset(self, app):
        response = app.post(
            url_for("dataset.delete", id="schrodingersdatset"),
            expect_errors=True,
        )
        assert 404 == response.status_int

    def test_sysadmin_can_delete_any_dataset(self, app):
        owner_org = factories.Organization()
        dataset = factories.Dataset(owner_org=owner_org["id"])

        user = factories.Sysadmin()
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        response = app.post(
            url_for("dataset.delete", id=dataset["name"]), extra_environ=env
        )
        response = response.follow()
        assert 200 == response.status_int

        deleted = helpers.call_action("package_show", id=dataset["id"])
        assert "deleted" == deleted["state"]

    def test_anon_user_cannot_delete_owned_dataset(self, app):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])

        response = app.post(
            url_for("dataset.delete", id=dataset["name"]), status=403
        )
        response.mustcontain("Unauthorized to delete package")

        deleted = helpers.call_action("package_show", id=dataset["id"])
        assert "active" == deleted["state"]

    def test_logged_in_user_cannot_delete_owned_dataset(self, app):
        owner = factories.User()
        owner_org = factories.Organization(
            users=[{"name": owner["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])

        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.post(
            url_for("dataset.delete", id=dataset["name"]),
            extra_environ=env,
            expect_errors=True,
        )
        assert 403 == response.status_int
        response.mustcontain("Unauthorized to delete package")

    def test_confirm_cancel_delete(self, app):
        """Test confirmation of deleting datasets

        When package_delete is made as a get request, it should return a
        'do you want to delete this dataset? confirmation page"""
        user = factories.User()
        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.delete", id=dataset["name"]), extra_environ=env
        )
        assert 200 == response.status_int
        message = "Are you sure you want to delete dataset - {name}?"
        response.mustcontain(message.format(name=dataset["title"]))

        form = response.forms["confirm-dataset-delete-form"]
        response = form.submit("cancel")
        response = helpers.webtest_maybe_follow(response, extra_environ=env)
        assert 200 == response.status_int


@pytest.mark.usefixtures("clean_db")
class TestResourceNew(object):
    def test_manage_dataset_resource_listing_page(self, app):
        user = factories.User()
        organization = factories.Organization(user=user)
        dataset = factories.Dataset(owner_org=organization["id"])
        resource = factories.Resource(package_id=dataset["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.resources", id=dataset["name"]), extra_environ=env
        )
        assert resource["name"] in response
        assert resource["description"] in response
        assert resource["format"] in response

    def test_unauth_user_cannot_view_manage_dataset_resource_listing_page(
        self, app
    ):
        user = factories.User()
        organization = factories.Organization(user=user)
        dataset = factories.Dataset(owner_org=organization["id"])
        resource = factories.Resource(package_id=dataset["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.resources", id=dataset["name"]), extra_environ=env
        )
        assert resource["name"] in response
        assert resource["description"] in response
        assert resource["format"] in response

    def test_404_on_manage_dataset_resource_listing_page_that_does_not_exist(
        self, app
    ):
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.resources", id="does-not-exist"),
            extra_environ=env,
            expect_errors=True,
        )
        assert 404 == response.status_int

    def test_add_new_resource_with_link_and_download(self, app):
        user = factories.User()
        dataset = factories.Dataset()
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        response = app.get(
            url_for("resource.new", id=dataset["id"]), extra_environ=env
        )

        form = response.forms["resource-edit"]
        form["url"] = u"http://test.com/"
        response = submit_and_follow(
            app, form, env, "save", "go-dataset-complete"
        )

        result = helpers.call_action("package_show", id=dataset["id"])
        response = app.get(
            url_for(
                "resource.download",
                id=dataset["id"],
                resource_id=result["resources"][0]["id"],
            ),
            extra_environ=env,
        )
        assert 302 == response.status_int

    def test_editor_can_add_new_resource(self, app):
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "editor"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        response = app.get(
            url_for("resource.new", id=dataset["id"]), extra_environ=env
        )

        form = response.forms["resource-edit"]
        form["name"] = u"test resource"
        form["url"] = u"http://test.com/"
        response = submit_and_follow(
            app, form, env, "save", "go-dataset-complete"
        )

        result = helpers.call_action("package_show", id=dataset["id"])
        assert 1 == len(result["resources"])
        assert u"test resource" == result["resources"][0]["name"]

    def test_admin_can_add_new_resource(self, app):
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        response = app.get(
            url_for("resource.new", id=dataset["id"]), extra_environ=env
        )

        form = response.forms["resource-edit"]
        form["name"] = u"test resource"
        form["url"] = u"http://test.com/"
        response = submit_and_follow(
            app, form, env, "save", "go-dataset-complete"
        )

        result = helpers.call_action("package_show", id=dataset["id"])
        assert 1 == len(result["resources"])
        assert u"test resource" == result["resources"][0]["name"]

    def test_member_cannot_add_new_resource(self, app):
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        response = app.get(
            url_for("resource.new", id=dataset["id"]),
            extra_environ=env,
            status=403,
        )

        response = app.post(
            url_for("resource.new", id=dataset["id"]),
            {"name": "test", "url": "test", "save": "save", "id": ""},
            extra_environ=env,
            status=403,
        )

    def test_non_organization_users_cannot_add_new_resource(self, app):
        """on an owned dataset"""
        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        response = app.get(
            url_for("resource.new", id=dataset["id"]),
            extra_environ=env,
            status=403,
        )

        response = app.post(
            url_for("resource.new", id=dataset["id"]),
            {"name": "test", "url": "test", "save": "save", "id": ""},
            extra_environ=env,
            status=403,
        )

    def test_anonymous_users_cannot_add_new_resource(self, app):
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"])

        response = app.get(
            url_for("resource.new", id=dataset["id"]), status=403
        )

        response = app.post(
            url_for("resource.new", id=dataset["id"]),
            {"name": "test", "url": "test", "save": "save", "id": ""},
            status=403,
        )

    def test_anonymous_users_cannot_edit_resource(self, app):
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"])
        resource = factories.Resource(package_id=dataset["id"])

        with app.flask_app.test_request_context():
            response = app.get(
                url_for(
                    "resource.edit",
                    id=dataset["id"],
                    resource_id=resource["id"],
                ),
                status=403,
            )

            response = app.post(
                url_for(
                    "resource.edit",
                    id=dataset["id"],
                    resource_id=resource["id"],
                ),
                {"name": "test", "url": "test", "save": "save", "id": ""},
                status=403,
            )


@pytest.mark.ckan_config("ckan.plugins", "image_view")
@pytest.mark.usefixtures("clean_db", "with_plugins")
class TestResourceView(object):
    def test_resource_view_create(self, app):
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])

        url = url_for(
            "resource.edit_view",
            id=resource["package_id"],
            resource_id=resource["id"],
            view_type="image_view",
        )

        response = app.post(
            url, {"title": "Test Image View"}, extra_environ=env
        ).follow(extra_environ=env)
        response.mustcontain("Test Image View")

    def test_resource_view_edit(self, app):
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])

        resource_view = factories.ResourceView(resource_id=resource["id"])
        url = url_for(
            "resource.edit_view",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )

        response = app.post(
            url, {"title": "Updated RV Title"}, extra_environ=env
        ).follow(extra_environ=env)
        response.mustcontain("Updated RV Title")

    def test_resource_view_delete(self, app):
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}

        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])

        resource_view = factories.ResourceView(resource_id=resource["id"])
        url = url_for(
            "resource.edit_view",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )

        response = app.post(
            url, {"delete": "Delete"}, extra_environ=env
        ).follow(extra_environ=env)
        response.mustcontain("This resource has no views")

    def test_existent_resource_view_page_returns_ok_code(self, app):
        resource_view = factories.ResourceView()

        url = url_for(
            "resource.read",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )

        app.get(url, status=200)

    def test_inexistent_resource_view_page_returns_not_found_code(self, app):
        resource_view = factories.ResourceView()

        url = url_for(
            "resource.read",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id="inexistent-view-id",
        )

        app.get(url, status=404)

    def test_resource_view_description_is_rendered_as_markdown(self, app):
        resource_view = factories.ResourceView(description="Some **Markdown**")
        url = url_for(
            "resource.read",
            id=resource_view["package_id"],
            resource_id=resource_view["resource_id"],
            view_id=resource_view["id"],
        )
        response = app.get(url)
        response.mustcontain("Some <strong>Markdown</strong>")


@pytest.mark.usefixtures("clean_db")
class TestResourceRead(object):
    def test_existing_resource_with_not_associated_dataset(self, app):

        dataset = factories.Dataset()
        resource = factories.Resource()

        url = url_for(
            "resource.read", id=dataset["id"], resource_id=resource["id"]
        )

        app.get(url, status=404)

    def test_resource_read_logged_in_user(self, app):
        """
        A logged-in user can view resource page.
        """
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"])

        url = url_for(
            "resource.read", id=dataset["id"], resource_id=resource["id"]
        )

        app.get(url, status=200, extra_environ=env)

    def test_resource_read_anon_user(self, app):
        """
        An anon user can view resource page.
        """
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"])

        url = url_for(
            "resource.read", id=dataset["id"], resource_id=resource["id"]
        )

        app.get(url, status=200)

    def test_resource_read_sysadmin(self, app):
        """
        A sysadmin can view resource page.
        """
        sysadmin = factories.Sysadmin()
        env = {"REMOTE_USER": sysadmin["name"].encode("ascii")}
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"])

        url = url_for(
            "resource.read", id=dataset["id"], resource_id=resource["id"]
        )

        app.get(url, status=200, extra_environ=env)

    def test_user_not_in_organization_cannot_read_private_dataset(self, app):
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        resource = factories.Resource(package_id=dataset["id"])

        url = url_for(
            "resource.read", id=dataset["id"], resource_id=resource["id"]
        )

        response = app.get(url, status=404, extra_environ=env)

    def test_organization_members_can_read_resources_in_private_datasets(
        self, app
    ):
        members = {
            "member": factories.User(),
            "editor": factories.User(),
            "admin": factories.User(),
            "sysadmin": factories.Sysadmin(),
        }
        organization = factories.Organization(
            users=[
                {"name": members["member"]["id"], "capacity": "member"},
                {"name": members["editor"]["id"], "capacity": "editor"},
                {"name": members["admin"]["id"], "capacity": "admin"},
            ]
        )
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        resource = factories.Resource(package_id=dataset["id"])

        for user, user_dict in members.items():
            response = app.get(
                url_for(
                    "resource.read",
                    id=dataset["name"],
                    resource_id=resource["id"],
                ),
                extra_environ={
                    "REMOTE_USER": user_dict["name"].encode("ascii")
                },
            )
            assert "Just another test resource" in response.body

    def test_anonymous_users_cannot_read_private_datasets(self, app):
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        response = app.get(
            url_for("dataset.read", id=dataset["name"]), status=404
        )
        assert 404 == response.status_int


@pytest.mark.usefixtures("clean_db")
class TestResourceDelete(object):
    def test_dataset_owners_can_delete_resources(self, app):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.post(
            url_for(
                "resource.delete",
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
        )
        response = response.follow()
        assert 200 == response.status_int
        response.mustcontain("This dataset has no data")

        with pytest.raises(p.toolkit.ObjectNotFound):
            helpers.call_action("resource_show", id=resource["id"])

    def test_deleting_non_existing_resource_404s(self, app):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.post(
            url_for(
                "resource.delete",
                id=dataset["name"],
                resource_id="doesnotexist",
            ),
            extra_environ=env,
            expect_errors=True,
        )
        assert 404 == response.status_int

    def test_anon_users_cannot_delete_owned_resources(self, app):
        user = factories.User()
        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])

        response = app.post(
            url_for(
                "resource.delete",
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            status=403,
        )
        response.mustcontain("Unauthorized to delete package")

    def test_logged_in_users_cannot_delete_resources_they_do_not_own(
        self, app
    ):
        # setup our dataset
        owner = factories.User()
        owner_org = factories.Organization(
            users=[{"name": owner["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])

        # access as another user
        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.post(
            url_for(
                "resource.delete",
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
            expect_errors=True,
        )
        assert 403 == response.status_int
        response.mustcontain("Unauthorized to delete package")

    def test_sysadmins_can_delete_any_resource(self, app):
        owner_org = factories.Organization()
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])

        sysadmin = factories.Sysadmin()
        env = {"REMOTE_USER": sysadmin["name"].encode("ascii")}
        response = app.post(
            url_for(
                "resource.delete",
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
        )
        response = response.follow()
        assert 200 == response.status_int
        response.mustcontain("This dataset has no data")

        with pytest.raises(p.toolkit.ObjectNotFound):
            helpers.call_action("resource_show", id=resource["id"])

    def test_confirm_and_cancel_deleting_a_resource(self, app):
        """Test confirmation of deleting resources

        When resource_delete is made as a get request, it should return a
        'do you want to delete this reource? confirmation page"""
        user = factories.User()
        owner_org = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=owner_org["id"])
        resource = factories.Resource(package_id=dataset["id"])
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for(
                "resource.delete",
                id=dataset["name"],
                resource_id=resource["id"],
            ),
            extra_environ=env,
        )
        assert 200 == response.status_int
        message = "Are you sure you want to delete resource - {name}?"
        response.mustcontain(message.format(name=resource["name"]))

        # cancelling sends us back to the resource edit page
        form = response.forms["confirm-resource-delete-form"]
        response = form.submit("cancel")
        response = response.follow(extra_environ=env)
        assert 200 == response.status_int


@pytest.mark.usefixtures("clean_db", "clean_index")
class TestSearch(object):
    def test_search_basic(self, app):
        dataset1 = factories.Dataset()

        offset = url_for("dataset.search")
        page = app.get(offset)

        assert dataset1["name"] in page.body.decode("utf8")

    def test_search_language_toggle(self, app):
        dataset1 = factories.Dataset()

        with app.flask_app.test_request_context():
            offset = url_for("dataset.search", q=dataset1["name"])
        page = app.get(offset)

        assert dataset1["name"] in page.body.decode("utf8")
        assert ("q=" + dataset1["name"]) in page.body.decode("utf8")

    def test_search_sort_by_blank(self, app):
        factories.Dataset()

        # ?sort has caused an exception in the past
        offset = url_for("dataset.search") + "?sort"
        app.get(offset)

    def test_search_sort_by_bad(self, app):
        factories.Dataset()

        # bad spiders try all sorts of invalid values for sort. They should get
        # a 400 error with specific error message. No need to alert the
        # administrator.
        offset = url_for("dataset.search") + "?sort=gvgyr_fgevat+nfp"
        response = app.get(offset, status=[200, 400])
        if response.status == 200:
            import sys

            sys.stdout.write(response.body)
            raise Exception(
                "Solr returned an unknown error message. "
                "Please check the error handling "
                "in ckan/lib/search/query.py:run"
            )

    def test_search_solr_syntax_error(self, app):
        factories.Dataset()

        # SOLR raises SyntaxError when it can't parse q (or other fields?).
        # Whilst this could be due to a bad user input, it could also be
        # because CKAN mangled things somehow and therefore we flag it up to
        # the administrator and give a meaningless error, just in case
        offset = url_for("dataset.search") + "?q=--included"
        search_response = app.get(offset)

        search_response_html = BeautifulSoup(search_response.body)
        err_msg = search_response_html.select("#search-error")
        err_msg = "".join([n.text for n in err_msg])
        assert "error while searching" in err_msg

    def test_search_plugin_hooks(self, app):
        with p.use_plugin("test_package_controller_plugin") as plugin:

            offset = url_for("dataset.search")
            app.get(offset)

            # get redirected ...
            assert plugin.calls["before_search"] == 1, plugin.calls
            assert plugin.calls["after_search"] == 1, plugin.calls

    def test_search_page_request(self, app):
        """Requesting package search page returns list of datasets."""

        factories.Dataset(name="dataset-one", title="Dataset One")
        factories.Dataset(name="dataset-two", title="Dataset Two")
        factories.Dataset(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)

        assert "3 datasets found" in search_response

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 3
        assert "Dataset One" in ds_titles
        assert "Dataset Two" in ds_titles
        assert "Dataset Three" in ds_titles

    def test_search_page_results(self, app):
        """Searching for datasets returns expected results."""

        factories.Dataset(name="dataset-one", title="Dataset One")
        factories.Dataset(name="dataset-two", title="Dataset Two")
        factories.Dataset(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)

        search_form = search_response.forms["dataset-search-form"]
        search_form["q"] = "One"
        search_results = webtest_submit(search_form)

        assert "1 dataset found" in search_results

        search_response_html = BeautifulSoup(search_results.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 1
        assert "Dataset One" in ds_titles

    def test_search_page_no_results(self, app):
        """Search with non-returning phrase returns no results."""

        factories.Dataset(name="dataset-one", title="Dataset One")
        factories.Dataset(name="dataset-two", title="Dataset Two")
        factories.Dataset(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)

        search_form = search_response.forms["dataset-search-form"]
        search_form["q"] = "Nout"
        search_results = webtest_submit(search_form)

        assert 'No datasets found for "Nout"' in search_results

        search_response_html = BeautifulSoup(search_results.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 0

    def test_search_page_results_tag(self, app):
        """Searching with a tag returns expected results."""

        factories.Dataset(
            name="dataset-one", title="Dataset One", tags=[{"name": "my-tag"}]
        )
        factories.Dataset(name="dataset-two", title="Dataset Two")
        factories.Dataset(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)
        assert "/dataset/?tags=my-tag" in search_response

        tag_search_response = app.get("/dataset?tags=my-tag")

        assert "1 dataset found" in tag_search_response

        search_response_html = BeautifulSoup(tag_search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 1
        assert "Dataset One" in ds_titles

    def test_search_page_results_tags(self, app):
        """Searching with a tag returns expected results with multiple tags"""

        factories.Dataset(
            name="dataset-one",
            title="Dataset One",
            tags=[
                {"name": "my-tag-1"},
                {"name": "my-tag-2"},
                {"name": "my-tag-3"},
            ],
        )
        factories.Dataset(name="dataset-two", title="Dataset Two")
        factories.Dataset(name="dataset-three", title="Dataset Three")

        params = "/dataset/?tags=my-tag-1&tags=my-tag-2&tags=my-tag-3"
        tag_search_response = app.get(params)

        assert "1 dataset found" in tag_search_response

        search_response_html = BeautifulSoup(tag_search_response.body)
        ds_titles = search_response_html.select(".filtered")
        assert len(ds_titles) == 3

    def test_search_page_results_private(self, app):
        """Private datasets don't show up in dataset search results."""
        org = factories.Organization()

        factories.Dataset(
            name="dataset-one",
            title="Dataset One",
            owner_org=org["id"],
            private=True,
        )
        factories.Dataset(name="dataset-two", title="Dataset Two")
        factories.Dataset(name="dataset-three", title="Dataset Three")

        search_url = url_for("dataset.search")
        search_response = app.get(search_url)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        ds_titles = [n.string for n in ds_titles]

        assert len(ds_titles) == 2
        assert "Dataset One" not in ds_titles
        assert "Dataset Two" in ds_titles
        assert "Dataset Three" in ds_titles

    def test_user_not_in_organization_cannot_search_private_datasets(
        self, app
    ):

        user = factories.User()
        organization = factories.Organization()
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == []

    def test_user_in_organization_can_search_private_datasets(self, app):

        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = factories.Dataset(
            title="A private dataset",
            owner_org=organization["id"],
            private=True,
        )
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == ["A private dataset"]

    def test_user_in_different_organization_cannot_search_private_datasets(
        self, app
    ):
        user = factories.User()
        org1 = factories.Organization(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        org2 = factories.Organization()
        dataset = factories.Dataset(
            title="A private dataset", owner_org=org2["id"], private=True
        )
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == []

    @pytest.mark.ckan_config("ckan.search.default_include_private", "false")
    def test_search_default_include_private_false(self, app):
        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "member"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"], private=True)
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == []

    def test_sysadmin_can_search_private_datasets(self, app):
        user = factories.Sysadmin()
        organization = factories.Organization()
        dataset = factories.Dataset(
            title="A private dataset",
            owner_org=organization["id"],
            private=True,
        )
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        search_url = url_for("dataset.search")
        search_response = app.get(search_url, extra_environ=env)

        search_response_html = BeautifulSoup(search_response.body)
        ds_titles = search_response_html.select(
            ".dataset-list " ".dataset-item " ".dataset-heading a"
        )
        assert [n.string for n in ds_titles] == ["A private dataset"]


@pytest.mark.usefixtures("clean_db")
class TestPackageFollow(object):
    def test_package_follow(self, app):

        user = factories.User()
        package = factories.Dataset()

        env = {"REMOTE_USER": user["name"].encode("ascii")}
        follow_url = url_for("dataset.follow", id=package["id"])
        response = app.post(follow_url, extra_environ=env, status=302)
        response = response.follow()
        assert "You are now following {0}".format(package["title"]) in response

    def test_package_follow_not_exist(self, app):
        """Pass an id for a package that doesn't exist"""

        user_one = factories.User()

        env = {"REMOTE_USER": user_one["name"].encode("ascii")}
        follow_url = url_for("dataset.follow", id="not-here")
        response = app.post(follow_url, extra_environ=env, status=302)
        response = response.follow(status=404)
        assert "Dataset not found" in response

    def test_package_unfollow(self, app):

        user_one = factories.User()
        package = factories.Dataset()

        env = {"REMOTE_USER": user_one["name"].encode("ascii")}
        follow_url = url_for("dataset.follow", id=package["id"])
        app.post(follow_url, extra_environ=env, status=302)

        unfollow_url = url_for("dataset.unfollow", id=package["id"])
        unfollow_response = app.post(
            unfollow_url, extra_environ=env, status=302
        )
        unfollow_response = unfollow_response.follow()

        assert (
            "You are no longer following {0}".format(package["title"])
            in unfollow_response
        )

    def test_package_unfollow_not_following(self, app):
        """Unfollow a package not currently following"""

        user_one = factories.User()
        package = factories.Dataset()

        env = {"REMOTE_USER": user_one["name"].encode("ascii")}
        unfollow_url = url_for("dataset.unfollow", id=package["id"])
        unfollow_response = app.post(
            unfollow_url, extra_environ=env, status=302
        )
        unfollow_response = unfollow_response.follow()  # /package/[id] 302s to
        unfollow_response = unfollow_response.follow()  # /package/[name]

        assert (
            "You are not following {0}".format(package["id"])
            in unfollow_response
        )

    def test_package_unfollow_not_exist(self, app):
        """Unfollow a package that doesn't exist."""

        user_one = factories.User()

        env = {"REMOTE_USER": user_one["name"].encode("ascii")}
        unfollow_url = url_for("dataset.unfollow", id="not-here")
        unfollow_response = app.post(
            unfollow_url, extra_environ=env, status=302
        )
        unfollow_response = unfollow_response.follow(status=404)
        assert "Dataset not found" in unfollow_response

    def test_package_follower_list(self, app):
        """Following users appear on followers list page."""

        user_one = factories.Sysadmin()
        package = factories.Dataset()

        env = {"REMOTE_USER": user_one["name"].encode("ascii")}
        follow_url = url_for("dataset.follow", id=package["id"])
        app.post(follow_url, extra_environ=env, status=302)

        followers_url = url_for("dataset.followers", id=package["id"])

        # Only sysadmins can view the followers list pages
        followers_response = app.get(
            followers_url, extra_environ=env, status=200
        )
        assert user_one["display_name"] in followers_response


@pytest.mark.usefixtures("clean_db")
class TestDatasetRead(object):
    def test_dataset_read(self, app):

        dataset = factories.Dataset()

        url = url_for("dataset.read", id=dataset["name"])
        response = app.get(url)
        assert dataset["title"] in response

    def test_redirect_when_given_id(self, app):
        dataset = factories.Dataset()
        response = app.get(
            url_for("dataset.read", id=dataset["id"]), status=302
        )
        # redirect replaces the ID with the name in the URL
        redirected_response = response.follow()
        expected_url = url_for("dataset.read", id=dataset["name"])
        assert redirected_response.request.path == expected_url
        assert redirected_response.request.query_string == ""

    def test_redirect_also_with_activity_parameter(self, app):
        dataset = factories.Dataset()
        activity = activity_model.package_activity_list(
            dataset["id"], limit=1, offset=0
        )[0]
        # view as an admin because viewing the old versions of a dataset
        sysadmin = factories.Sysadmin()
        env = {"REMOTE_USER": sysadmin["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.read", id=dataset["id"], activity_id=activity.id),
            status=302,
            extra_environ=env,
        )
        redirected_response = response.follow(extra_environ=env)
        expected_path = url_for("dataset.read", id=dataset["name"])
        assert redirected_response.request.path == expected_path
        assert (
            redirected_response.request.query_string
            == "activity_id={}".format(activity.id)
        )

    def test_no_redirect_loop_when_name_is_the_same_as_the_id(self, app):
        dataset = factories.Dataset(id="abc", name="abc")
        app.get(
            url_for("dataset.read", id=dataset["id"]), status=200
        )  # ie no redirect


@pytest.mark.usefixtures("clean_db")
class TestActivity(object):
    def test_simple(self, app):
        """Checking the template shows the activity stream."""
        user = factories.User()
        dataset = factories.Dataset(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert "Mr. Test User" in response
        assert "created the dataset" in response

    def test_create_dataset(self, app):

        user = factories.User()
        dataset = factories.Dataset(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "created the dataset" in response
        assert (
            '<a href="/dataset/{}">Test Dataset'.format(dataset["id"])
            in response
        )

    def _clear_activities(self):
        model.Session.query(model.Activity).delete()
        model.Session.flush()

    def test_change_dataset(self, app):

        user = factories.User()
        dataset = factories.Dataset(user=user)
        self._clear_activities()
        dataset["title"] = "Dataset with changed title"
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">Dataset with changed title'.format(
                dataset["id"]
            )
            in response
        )

    def test_create_tag_directly(self, app):

        user = factories.User()
        dataset = factories.Dataset(user=user)
        self._clear_activities()
        dataset["tags"] = [{"name": "some_tag"}]
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_create_tag(self, app):
        user = factories.User()
        dataset = factories.Dataset(user=user)
        self._clear_activities()
        dataset["tags"] = [{"name": "some_tag"}]
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_create_extra(self, app):
        user = factories.User()
        dataset = factories.Dataset(user=user)
        self._clear_activities()
        dataset["extras"] = [{"key": "some", "value": "extra"}]
        helpers.call_action(
            "package_update", context={"user": user["name"]}, **dataset
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_create_resource(self, app):
        user = factories.User()
        dataset = factories.Dataset(user=user)
        self._clear_activities()
        helpers.call_action(
            "resource_create",
            context={"user": user["name"]},
            name="Test resource",
            package_id=dataset["id"],
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_update_resource(self, app):
        user = factories.User()
        dataset = factories.Dataset(user=user)
        resource = factories.Resource(package_id=dataset["id"])
        self._clear_activities()

        helpers.call_action(
            "resource_update",
            context={"user": user["name"]},
            id=resource["id"],
            name="Test resource updated",
            package_id=dataset["id"],
        )

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">{}'.format(dataset["id"], dataset["title"])
            in response
        )

        activities = helpers.call_action(
            "package_activity_list", id=dataset["id"]
        )

        assert len(activities) == 1

    def test_delete_dataset(self, app):
        user = factories.User()
        org = factories.Organization()
        dataset = factories.Dataset(owner_org=org["id"], user=user)
        self._clear_activities()
        helpers.call_action(
            "package_delete", context={"user": user["name"]}, **dataset
        )

        url = url_for("organization.activity", id=org["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "deleted the dataset" in response
        assert (
            '<a href="/dataset/{}">Test Dataset'.format(dataset["id"])
            in response
        )

    def test_admin_can_see_old_versions(self, app):

        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        dataset = factories.Dataset(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url, extra_environ=env)
        assert "View this version" in response

    def test_public_cant_see_old_versions(self, app):

        user = factories.User()
        dataset = factories.Dataset(user=user)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert "View this version" not in response

    def test_admin_can_see_changes(self, app):

        user = factories.User()
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        dataset = factories.Dataset()  # activities by system user aren't shown
        dataset["title"] = "Changed"
        helpers.call_action("package_update", **dataset)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url, extra_environ=env)
        assert "Changes" in response
        changes_page = response.click("Changes", extra_environ=env)

    def test_public_cant_see_changes(self, app):
        dataset = factories.Dataset()  # activities by system user aren't shown
        dataset["title"] = "Changed"
        helpers.call_action("package_update", **dataset)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert "Changes" not in response

    def test_legacy_changed_package_activity(self, app):
        """Render an activity that was created with an earlier version of CKAN,
        and it has not been migrated (with migrate_package_activity.py)
        """

        user = factories.User()
        dataset = factories.Dataset(user=user)

        # delete the modern Activity object that's been automatically created
        modern_activity = (
            model.Session.query(model.Activity)
            .filter_by(object_id=dataset["id"])
            .one()
        )
        modern_activity.delete()

        # Create an Activity object as it was in earlier versions of CKAN.
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L508
        activity_type = "changed"
        dataset_table_dict = dictization.table_dictize(
            model.Package.get(dataset["id"]), context={"model": model}
        )
        activity = model.Activity(
            user_id=user["id"],
            object_id=dataset["id"],
            activity_type="%s package" % activity_type,
            data={
                # "actor": a legacy activity had no "actor"
                # "package": a legacy activity had just the package table,
                # rather than the result of package_show
                "package": dataset_table_dict
            },
        )
        model.Session.add(activity)
        # a legacy activity had a ActivityDetail associated with the Activity
        # This code is based on:
        # https://github.com/ckan/ckan/blob/b348bf2fe68db6704ea0a3e22d533ded3d8d4344/ckan/model/package.py#L542
        activity_detail = model.ActivityDetail(
            activity_id=activity.id,
            object_id=dataset["id"],
            object_type=u"Package",
            activity_type=activity_type,
            data={u"package": dataset_table_dict},
        )
        model.Session.add(activity_detail)
        model.Session.flush()

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        assert "updated the dataset" in response
        assert (
            '<a href="/dataset/{}">Test Dataset'.format(dataset["id"])
            in response
        )

    # ckanext-canada uses their IActivity to add their custom activity to the
    # list of validators: https://github.com/open-data/ckanext-canada/blob/6870e5bc38a04aa8cef191b5e9eb361f9560872b/ckanext/canada/plugins.py#L596
    # but it's easier here to just hack patch it in
    @mock.patch(
        "ckan.logic.validators.object_id_validators",
        dict(
            object_id_validators.items()
            + [("changed datastore", package_id_exists)]
        ),
    )
    def test_custom_activity(self, app):
        """Render a custom activity
        """

        user = factories.User()
        organization = factories.Organization(
            users=[{"name": user["id"], "capacity": "admin"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"], user=user)
        resource = factories.Resource(package_id=dataset["id"])
        self._clear_activities()

        # Create a custom Activity object. This one is inspired by:
        # https://github.com/open-data/ckanext-canada/blob/master/ckanext/canada/activity.py
        activity_dict = {
            "user_id": user["id"],
            "object_id": dataset["id"],
            "activity_type": "changed datastore",
            "data": {
                "resource_id": resource["id"],
                "pkg_type": dataset["type"],
                "resource_name": "june-2018",
                "owner_org": organization["name"],
                "count": 5,
            },
        }
        helpers.call_action("activity_create", **activity_dict)

        url = url_for("dataset.activity", id=dataset["id"])
        response = app.get(url)
        assert (
            '<a href="/user/{}">Mr. Test User'.format(user["name"]) in response
        )
        # it renders the activity with fallback.html, since we've not defined
        # changed_datastore.html in this case
        assert "changed datastore" in response


@pytest.mark.usefixtures("clean_db")
class TestChanges(object):  # i.e. the diff
    def test_simple(self, app):
        user = factories.User()
        dataset = factories.Dataset(title="First title", user=user)
        dataset["title"] = "Second title"
        helpers.call_action("package_update", **dataset)

        activity = activity_model.package_activity_list(
            dataset["id"], limit=1, offset=0
        )[0]
        env = {"REMOTE_USER": user["name"].encode("ascii")}
        response = app.get(
            url_for("dataset.changes", id=activity.id), extra_environ=env
        )
        response.mustcontain("First")
        response.mustcontain("Second")
