"""
    Client Interface for POEditor API (https://poeditor.com).

    Usage:

    >>> from poeditor import Client
    >>> client = Client(api_token='my_token')
    >>> projects = client.list_projects()
"""

import json
import tempfile
import warnings
from typing import Any, Dict

import requests

from poeditor.exceptions import POEditorArgsException, POEditorException
from poeditor.utils import parse_datetime

__all__ = ["Client"]


class Client(object):
    """
    Connect your software to POEditor with its simple API
    Please refers to https://poeditor.com/docs/api if you have questions
    """

    BASE = "https://api.poeditor.com/v2"

    SUCCESS_CODE = "success"
    FILE_TYPES = [
        "po",
        "pot",
        "mo",
        "xls",
        "csv",
        "resx",
        "resw",
        "android_strings",
        "apple_strings",
        "xliff",
        "properties",
        "key_value_json",
        "json",
        "xmb",
        "xtb",
    ]
    FILTER_BY = [
        "translated",
        "untranslated",
        "fuzzy",
        "not_fuzzy",
        "automatic",
        "not_automatic",
        "proofread",
        "not_proofread",
    ]

    UPDATING_TERMS = "terms"
    UPDATING_TERMS_TRANSLATIONS = "terms_translations"
    UPDATING_TRANSLATIONS = "translations"

    # in seconds. Upload: No more than one request every 30 seconds
    MIN_UPLOAD_INTERVAL = 30

    def __init__(self, api_token):
        """
        All requests to the API must contain the parameter api_token.
        You'll find it in My Account > API Access in your POEditor account.
        """
        self.api_token = api_token

    def _url(self, path: str) -> str:
        """
        Returns an absolute url for a given path by prepending the api base url.
        """
        return f"{self.BASE}/{path}"

    def _make_request(self, path: str, payload: Dict[str, Any]) -> Any:

        if file := payload.pop("file", None):
            files = {"file": file}
        else:
            files = None

        response = requests.post(
            self._url(path),
            data=payload,
            files=files,
        )

        if not response.ok:
            raise POEditorException(
                status="fail",
                error_code=response.status_code,
                message=response.reason,
            )

        try:
            data = response.json()["response"]
        except ValueError:
            raise POEditorException(
                status="fail",
                error_code=-1,
                message="Could not parse json response",
            )
        except KeyError:
            raise POEditorException(
                status="fail",
                error_code=-1,
                message='"response" key is not present',
            )

        if data.get("status") != self.SUCCESS_CODE:
            raise POEditorException(
                error_code=data.get("code"),
                status=data.get("status"),
                message=data.get("message"),
            )

        return response.json()

    def _run(self, path: str, **kwargs):
        """
        Requests API
        """
        payload = kwargs
        payload.update({"api_token": self.api_token})

        return self._make_request(path, payload)

    def _project_formatter(self, data):
        """
        Project object
        """
        open_ = False if not data["open"] or data["open"] == "0" else True
        public = False if not data["public"] or data["public"] == "0" else True
        output = {
            "created": parse_datetime(data["created"]),
            "id": int(data["id"]),
            "name": data["name"],
            "open": open_,
            "public": public,
        }

        # the detail view returns more info than the list view
        # see https://poeditor.com/docs/api#projects_view
        for key in ["description", "reference_language", "terms"]:
            if key in data:
                output[key] = data[key]

        return output

    def list_projects(self):
        """
        Returns the list of projects owned by user.
        """
        data = self._run(path="projects/list")
        projects = data["result"].get("projects", [])
        return [self._project_formatter(item) for item in projects]

    def create_project(self, name, description=None):
        """
        creates a new project. Returns the id of the project (if successful)
        """
        description = description or ""
        data = self._run(path="projects/add", name=name, description=description)
        return data["result"]["project"]["id"]

    def update_project(
        self, project_id, name=None, description=None, reference_language=None
    ):
        """
        Updates project settings (name, description, reference language)
        If optional parameters are not sent, their respective fields are not updated.
        """
        kwargs = {}
        if name is not None:
            kwargs["name"] = name
        if description is not None:
            kwargs["description"] = description
        if reference_language is not None:
            kwargs["reference_language"] = reference_language

        data = self._run(path="projects/update", id=project_id, **kwargs)
        return data["result"]["project"]["id"]

    def delete_project(self, project_id):
        """
        Deletes the project from the account.
        You must be the owner of the project.
        """
        self._run(
            path="projects/delete",
            id=project_id,
        )
        return True

    def view_project_details(self, project_id):
        """
        Returns project's details.
        """
        data = self._run(path="projects/view", id=project_id)
        return self._project_formatter(data["result"]["project"])

    def list_project_languages(self, project_id):
        """
        Returns project languages, percentage of translation done for each and the
        datetime (UTC - ISO 8601) when the last change was made.
        """
        data = self._run(path="languages/list", id=project_id)
        return data["result"].get("languages", [])

    def add_language_to_project(self, project_id, language_code):
        """
        Adds a new language to project
        """
        self._run(path="languages/add", id=project_id, language=language_code)
        return True

    def delete_language_from_project(self, project_id, language_code):
        """
        Deletes existing language from project
        """
        self._run(path="languages/delete", id=project_id, language=language_code)
        return True

    def set_reference_language(self, project_id, language_code):
        """
        Sets a reference language to project
        """
        return self.update_project(project_id, reference_language=language_code)

    def view_project_terms(self, project_id, language_code=None):
        """
        Returns project's terms and translations if the argument language is provided.
        """
        data = self._run(path="terms/list", id=project_id, language=language_code)
        return data["result"].get("terms", [])

    def add_terms(self, project_id, data):
        """
        Adds terms to project.
        >>> data = [
            {
                "term": "Add new list",
                "context": "",
                "reference": "/projects",
                "plural": "",
                "comment": ""
            },
            {
                "term": "one project found",
                "context": "",
                "reference": "/projects",
                "plural": "%d projects found",
                "comment": "Make sure you translate the plural forms",
                "tags": [
                    "first_tag",
                    "second_tag"
                ]
            },
            {
                "term": "Show all projects",
                "context": "",
                "reference": "/projects",
                "plural": "",
                "tags": "just_a_tag"
            }
        ]
        """
        data = self._run(path="terms/add", id=project_id, data=json.dumps(data))
        return data["result"]["terms"]

    def delete_terms(self, project_id, data):
        """
        Deletes terms from project.
        >>> data = [
            {
                "term": "one project found",
                "context": ""
            },
            {
                "term": "Show all projects",
                "context": "form"
            }
        ]
        """
        data = self._run(path="terms/delete", id=project_id, data=json.dumps(data))
        return data["result"]["terms"]

    def add_comment(self, project_id, data):
        """
        Adds comments to existing terms.
        >>> data = [
                {
                    "term": "Add new list",
                    "context": "",
                    "comment": "This is a button"
                },
                {
                    "term": "one project found",
                    "context": "",
                    "comment": "Make sure you translate the plural forms"
                },
                {
                    "term": "Show all projects",
                    "context": "",
                    "comment": "This is a button"
                }
            ]
        """
        data = self._run(path="terms/add_comment", id=project_id, data=json.dumps(data))
        return data["result"]["terms"]

    def sync_terms(self, project_id, data):
        """
        Syncs your project with the array you send (terms that are not found
        in the dict object will be deleted from project and the new ones
        added).
        Please use with caution. If wrong data is sent, existing terms and their
        translations might be irreversibly lost.

        >>> data = [
            {
                "term": "Add new list",
                "context": "",
                "reference": "/projects",
                "plural": "",
                "comment": ""
            },
            {
                "term": "one project found",
                "context": "",
                "reference": "/projects",
                "plural": "%d projects found",
                "comment": "Make sure you translate the plural forms",
                "tags": [
                    "first_tag",
                    "second_tag"
                ]
            },
            {
                "term": "Show all projects",
                "context": "",
                "reference": "/projects",
                "plural": "",
                "tags": "just_a_tag"
            }
        ]
        """
        data = self._run(path="projects/sync", id=project_id, data=json.dumps(data))
        return data["result"]["terms"]

    def update_project_language(
        self, project_id, language_code, data, fuzzy_trigger=None
    ):
        """
        Inserts / overwrites translations.
        >>> data = [
            {
                "term": "Projects",
                "context": "project list",
                "translation": {
                    "content": "Des projets",
                    "fuzzy": 0
                }
            }
        ]
        """
        kwargs = {}
        if fuzzy_trigger is not None:
            kwargs["fuzzy_trigger"] = fuzzy_trigger

        data = self._run(
            path="languages/update",
            id=project_id,
            language=language_code,
            data=json.dumps(data),
            **kwargs,
        )
        return data["result"]["translations"]

    def export(
        self,
        project_id,
        language_code,
        file_type="po",
        filters=None,
        tags=None,
        local_file=None,
    ):
        """
        Return terms / translations

        filters - filter by self._filter_by
        tags - filter results by tags;
        local_file - save content into it. If None, save content into
            random temp file.

        >>> tags = 'name-of-tag'
        >>> tags = ["name-of-tag"]
        >>> tags = ["name-of-tag", "name-of-another-tag"]

        >>> filters = 'translated'
        >>> filters = ["translated"]
        >>> filters = ["translated", "not_fuzzy"]
        """
        if file_type not in self.FILE_TYPES:
            raise POEditorArgsException(
                "content_type: file format {}".format(self.FILE_TYPES)
            )

        if filters and isinstance(filters, str) and filters not in self.FILTER_BY:
            raise POEditorArgsException(
                "filters - filter results by {}".format(self.FILTER_BY)
            )
        elif filters and set(filters).difference(set(self.FILTER_BY)):
            raise POEditorArgsException(
                "filters - filter results by {}".format(self.FILTER_BY)
            )

        data = self._run(
            path="projects/export",
            id=project_id,
            language=language_code,
            type=file_type,
            filters=filters,
            tags=tags,
        )
        # The link of the file (expires after 10 minutes).
        file_url = data["result"]["url"]

        # Download file content:
        res = requests.get(file_url, stream=True)
        if not local_file:
            tmp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=".{}".format(file_type)
            )
            tmp_file.close()
            local_file = tmp_file.name

        with open(local_file, "w+b") as po_file:
            for data in res.iter_content(chunk_size=1024):
                po_file.write(data)
        return file_url, local_file

    def _upload(
        self,
        project_id,
        updating,
        file_path,
        language_code=None,
        overwrite=False,
        sync_terms=False,
        tags=None,
        fuzzy_trigger=None,
    ):
        """
        Internal: updates terms / translations

        File uploads are limited to one every 30 seconds
        """
        options = [
            self.UPDATING_TERMS,
            self.UPDATING_TERMS_TRANSLATIONS,
            self.UPDATING_TRANSLATIONS,
        ]
        if updating not in options:
            raise POEditorArgsException("Updating arg must be in {}".format(options))

        options = [self.UPDATING_TERMS_TRANSLATIONS, self.UPDATING_TRANSLATIONS]
        if language_code is None and updating in options:
            raise POEditorArgsException(
                "Language code is required only if updating is "
                "terms_translations or translations)"
            )

        if updating == self.UPDATING_TRANSLATIONS:
            tags = None
            sync_terms = None

        # Special content type:
        tags = tags or ""
        language_code = language_code or ""
        sync_terms = "1" if sync_terms else "0"
        overwrite = "1" if overwrite else "0"
        fuzzy_trigger = "1" if fuzzy_trigger else "0"
        project_id = str(project_id)

        with open(file_path, "r+b") as local_file:
            data = self._run(
                path="projects/upload",
                id=project_id,
                language=language_code,
                file=local_file,
                updating=updating,
                tags=tags,
                sync_terms=sync_terms,
                overwrite=overwrite,
                fuzzy_trigger=fuzzy_trigger,
            )
        return data["result"]

    def update_terms(
        self,
        project_id,
        file_path=None,
        language_code=None,
        overwrite=False,
        sync_terms=False,
        tags=None,
        fuzzy_trigger=None,
    ):
        """
        Updates terms

        overwrite: set it to True if you want to overwrite translations
        sync_terms: set it to True if you want to sync your terms (terms that
            are not found in the uploaded file will be deleted from project
            and the new ones added). Ignored if updating = translations
        tags: Add tags to the project terms; available when updating terms or terms_translations;
              you can use the following keys: "all" - for the all the imported terms, "new" - for
              the terms which aren't already in the project, "obsolete" - for the terms which are
              in the project but not in the imported file and "overwritten_translations" - for the
              terms for which translations change
        fuzzy_trigger: set it to True to mark corresponding translations from the
            other languages as fuzzy for the updated values
        """
        return self._upload(
            project_id=project_id,
            updating=self.UPDATING_TERMS,
            file_path=file_path,
            language_code=language_code,
            overwrite=overwrite,
            sync_terms=sync_terms,
            tags=tags,
            fuzzy_trigger=fuzzy_trigger,
        )

    def update_terms_definitions(
        self,
        project_id,
        file_path=None,
        language_code=None,
        overwrite=False,
        sync_terms=False,
        tags=None,
        fuzzy_trigger=None,
    ):
        warnings.warn(
            "This method has been renamed update_terms_translations",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.update_terms_translations(
            project_id,
            file_path,
            language_code,
            overwrite,
            sync_terms,
            tags,
            fuzzy_trigger,
        )

    def update_terms_translations(
        self,
        project_id,
        file_path=None,
        language_code=None,
        overwrite=False,
        sync_terms=False,
        tags=None,
        fuzzy_trigger=None,
    ):
        """
        Updates terms translations

        overwrite: set it to True if you want to overwrite translations
        sync_terms: set it to True if you want to sync your terms (terms that
            are not found in the uploaded file will be deleted from project
            and the new ones added). Ignored if updating = translations
        tags: Add tags to the project terms; available when updating terms or terms_translations;
              you can use the following keys: "all" - for the all the imported terms, "new" - for
              the terms which aren't already in the project, "obsolete" - for the terms which are
              in the project but not in the imported file and "overwritten_translations" - for the
              terms for which translations change
        fuzzy_trigger: set it to True to mark corresponding translations from the
            other languages as fuzzy for the updated values
        """
        return self._upload(
            project_id=project_id,
            updating=self.UPDATING_TERMS_TRANSLATIONS,
            file_path=file_path,
            language_code=language_code,
            overwrite=overwrite,
            sync_terms=sync_terms,
            tags=tags,
            fuzzy_trigger=fuzzy_trigger,
        )

    def update_definitions(
        self,
        project_id,
        file_path=None,
        language_code=None,
        overwrite=False,
        fuzzy_trigger=None,
    ):
        warnings.warn(
            "This method has been renamed update_translations",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.update_translations(
            project_id, file_path, language_code, overwrite, fuzzy_trigger
        )

    def update_translations(
        self,
        project_id,
        file_path=None,
        language_code=None,
        overwrite=False,
        fuzzy_trigger=None,
    ):
        """
        Updates translations

        overwrite: set it to True if you want to overwrite definitions
        fuzzy_trigger: set it to True to mark corresponding translations from the
            other languages as fuzzy for the updated values
        """
        return self._upload(
            project_id=project_id,
            updating=self.UPDATING_TRANSLATIONS,
            file_path=file_path,
            language_code=language_code,
            overwrite=overwrite,
            fuzzy_trigger=fuzzy_trigger,
        )

    def available_languages(self):
        """
        Returns a comprehensive list of all languages supported by POEditor.
        You can find it here (https://poeditor.com/docs/languages), too.
        """
        data = self._run(path="languages/available")
        return data["result"].get("languages", [])

    def list_contributors(self, project_id=None, language_code=None):
        """
        Returns the list of contributors
        """
        data = self._run(
            path="contributors/list", id=project_id, language=language_code
        )
        return data["result"].get("contributors", [])

    def add_contributor(self, project_id, name, email, language_code):
        """
        Adds a contributor to a project language
        """
        self._run(
            path="contributors/add",
            id=project_id,
            name=name,
            email=email,
            language=language_code,
        )
        return True

    def add_administrator(self, project_id, name, email):
        """
        Adds a contributor to a project language
        """
        self._run(
            path="contributors/add",
            id=project_id,
            name=name,
            email=email,
            admin=True,
        )
        return True

    def remove_contributor(self, project_id, email, language):
        """
        Removes a contributor
        """
        self._run(
            path="contributors/remove",
            id=project_id,
            email=email,
            language=language,
        )
        return True
