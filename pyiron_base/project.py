# coding: utf-8
# Copyright (c) Max-Planck-Institut für Eisenforschung GmbH - Computational Materials Design (CM) Department
# Distributed under the terms of "New BSD License", see the LICENSE file.

from __future__ import print_function
import os
import posixpath
import shutil
from pyiron_base.core.project.path import ProjectPath
from pyiron_base.core.settings.generic import Settings
from pyiron_base.core.settings.jobtable import get_db_columns, get_job_ids, get_job_id, get_jobs, job_table, \
    get_job_status, set_job_status, get_job_working_directory, get_child_ids
from pyiron_base.core.settings.logger import set_logging_level
from pyiron_base.objects.generic.hdfio import ProjectHDFio
from pyiron_base.objects.job.jobtype import JobType, JobTypeChoice
from pyiron_base.objects.server.queuestatus import queue_delete_job, queue_is_empty, queue_job_info, queue_table, \
    wait_for_job, queue_report, queue_id_table, queue_enable_reservation

"""
The project object is the central import point of pyiron - all other objects can be created from this one 
"""

__author__ = "Joerg Neugebauer, Jan Janssen"
__copyright__ = "Copyright 2017, Max-Planck-Institut für Eisenforschung GmbH - Computational Materials Design (CM) Department"
__version__ = "1.0"
__maintainer__ = "Jan Janssen"
__email__ = "janssen@mpie.de"
__status__ = "production"
__date__ = "Sep 1, 2017"

s = Settings()


class Project(ProjectPath):
    """
    The project is the central class in pyiron, all other objects can be created from the project object.

    Args:
        path (GenericPath, str): path of the project defined by GenericPath, absolute or relative (with respect to
                                     current working directory) path
        user (str): current pyiron user
        sql_query (str): SQL query to only select a subset of the existing jobs within the current project

    Attributes:

        .. attribute:: root_path

            the pyiron user directory, defined in the .pyiron configuration

        .. attribute:: project_path

            the relative path of the current project / folder starting from the root path
            of the pyiron user directory

        .. attribute:: path

            the absolute path of the current project / folder

        .. attribute:: base_name

            the name of the current project / folder

        .. attribute:: history

            previously opened projects / folders

        .. attribute:: parent_group

            parent project - one level above the current project

        .. attribute:: user

            current unix/linux/windows user who is running pyiron

        .. attribute:: sql_query

            an SQL query to limit the jobs within the project to a subset which matches the SQL query.

        .. attribute:: db

            connection to the SQL database

        .. attribute:: job_type

            Job Type object with all the available job types: ['ExampleJob', 'SerialMaster', 'ParallelMaster', 'ScriptJob',
                                                               'ListMaster']

        .. attribute:: view_mode

            If viewer_mode is enable pyiron has read only access to the database.

    """
    def __init__(self, path="", user=None, sql_query=None):
        super(Project, self).__init__(path=path)

        self.user = user
        self.sql_query = sql_query
        self._filter = ["groups", "nodes", "objects"]
        self._inspect_mode = False
        self._store = None

        db_name = s.top_path_dict[self.root_path]
        s.open_connection()
        self.db = s.db_dict[db_name]
        self.job_type = JobTypeChoice()

    @property
    def parent_group(self):
        """
        Get the parent group of the current project

        Returns:
            Project: parent project
        """
        return self.create_group("..")

    @property
    def view_mode(self):
        """
        Get viewer_mode - if viewer_mode is enable pyiron has read only access to the database.

        Returns:
            bool: returns TRUE when viewer_mode is enabled
        """
        return self.db.viewer_mode

    @property
    def name(self):
        """
        The name of the current project folder

        Returns:
            str: name of the current project folder
        """
        return self.base_name

    def copy(self):
        """
        Copy the project object - copying just the Python object but maintaining the same pyiron path

        Returns:
            Project: copy of the project object
        """
        new = Project(path=self.path, user=self.user, sql_query=self.sql_query)
        new._filter = self._filter
        new._inspect_mode = self._inspect_mode
        return new

    def copy_to(self, destination):
        """
        Copy the project object to a different pyiron path - including the content of the project (all jobs).
        
        Args:
            destination (Project): project path to copy the project content to

        Returns:
            Project: pointing to the new project path
        """
        if not self.view_mode:
            if not isinstance(destination, Project):
                raise TypeError('A project can only be copied to another project.')
            for sub_project_name in self.list_groups():
                if "_hdf5" not in sub_project_name:
                    sub_project = self.open(sub_project_name)
                    destination_sub_project = destination.open(sub_project_name)
                    sub_project.copy_to(destination_sub_project)
            for job_id in self.get_job_ids(recursive=False):
                ham = self.load(job_id)
                ham.copy_to(destination)
            for file in self.list_files():
                if '.h5' not in file:
                    shutil.copy(os.path.join(self.path, file), destination.path)
            return destination
        else:
            raise EnvironmentError('copy_to: is not available in Viewermode !')

    def create_from_job(self, job_old, new_job_name):
        """
        Create a new job from an existing pyiron job

        Args:
            job_old (GenericJob): Job to copy
            new_job_name (str): New job name

        Returns:
            GenericJob: New job with the new job name.
        """
        job_id = self.get_job_id(new_job_name)
        if job_id is not None:
            s.logger.info('create_from_job has already job_id {}!'.format(job_id))
            return None

        print('job_old: ', job_old.status)
        job_new = job_old.copy_to(self, new_job_name=new_job_name)
        s.logger.debug("create_job:: {} {} from id {}".format(self.path, new_job_name, job_old.job_id))
        return job_new

    def create_group(self, group):
        """
        Create a new subproject/ group/ folder

        Args:
            group (str): name of the new project

        Returns:
            Project: New subproject
        """
        new = self.copy()
        return new.open(group, history=False)

    def create_job(self, job_type, job_name):
        """
        Create one of the following jobs:
        - 'ExampleJob': example job just generating random number
        - 'SerialMaster': series of jobs run in serial
        - 'ParallelMaster': series of jobs run in parallel
        - 'ScriptJob': Python script or jupyter notebook job container
        - 'ListMaster': list of jobs

        Args:
            job_type (str): job type can be ['ExampleJob', 'SerialMaster', 'ParallelMaster', 'ScriptJob', 'ListMaster']
            job_name (str): name of the job

        Returns:
            GenericJob: job object depending on the job_type selected
        """
        job_name = job_name.replace('.','_')
        job = JobType(job_type, project=ProjectHDFio(project=self.copy(), file_name=job_name),
                      job_name=job_name)
        if self.user is not None:
            job.user = self.user
        return job

    def get_child_ids(self, job_specifier, project=None):
        """
        Get the childs for a specific job

        Args:
            job_specifier (str, int): name of the job or job ID
            project (Project): Project the job is located in - optional

        Returns:
            list: list of child IDs
        """
        if not project:
            project = self.project_path
        return get_child_ids(database=self.db, sql_query=self.sql_query, user=self.user, project_path=project,
                             job_specifier=job_specifier)

    def get_db_columns(self):
        """
        Get column names

        Returns:
            list: list of column names like:
                 ['id',
                 'parentid',
                 'masterid',
                 'projectpath',
                 'project',
                 'job',
                 'subjob',
                 'chemicalformula',
                 'status',
                 'hamilton',
                 'hamversion',
                 'username',
                 'computer',
                 'timestart',
                 'timestop',
                 'totalcputime']
        """
        return get_db_columns(self.db)

    def get_jobs(self, recursive=True, columns=["id", "project"]):
        """
        Internal function to return the jobs as dictionary rather than a pandas.Dataframe

        Args:
            recursive (bool): search subprojects [True/False]
            columns (list): by default only the columns ['id', 'project'] are selected, but the user can select a subset
                            of ['id', 'status', 'chemicalformula', 'job', 'subjob', 'project', 'projectpath', 'timestart',
                            'timestop', 'totalcputime', 'computer', 'hamilton', 'hamversion', 'parentid', 'masterid']

        Returns:
            dict: columns are used as keys and point to a list of the corresponding values
        """
        return get_jobs(database=self.db, sql_query=self.sql_query, user=self.user, project_path=self.project_path,
                        recursive=recursive, columns=columns)

    def get_job_ids(self, recursive=True):
        """
        Return the job IDs matching a specific query

        Args:
            recursive (bool): search subprojects [True/False]

        Returns:
            list: a list of job IDs
        """
        return get_job_ids(database=self.db, sql_query=self.sql_query, user=self.user, project_path=self.project_path,
                           recursive=recursive)

    def get_job_id(self, job_specifier):
        """
        get the job_id for job named job_name in the local project path from database

        Args:
            job_specifier (str, int): name of the job or job ID

        Returns:
            int: job ID of the job
        """
        return get_job_id(database=self.db, sql_query=self.sql_query, user=self.user, project_path=self.project_path,
                          job_specifier=job_specifier)

    def get_job_status(self, job_specifier, project=None):
        """
        Get the status of a particular job

        Args:
            job_specifier (str, int): name of the job or job ID
            project (Project): Project the job is located in - optional

        Returns:
            str: job status can be one of the following ['initialized', 'appended', 'created', 'submitted', 'running',
                 'aborted', 'collect', 'suspended', 'refresh', 'busy', 'finished']
        """
        if not project:
            project = self.project_path
        return get_job_status(database=self.db, sql_query=self.sql_query, user=self.user, project_path=project,
                              job_specifier=job_specifier)

    def get_job_working_directory(self, job_specifier, project=None):
        """
        Get the working directory of a particular job

        Args:
            job_specifier (str, int): name of the job or job ID
            project (Project): Project the job is located in - optional

        Returns:
            str: working directory as absolute path
        """
        if not project:
            project = self.project_path
        return get_job_working_directory(database=self.db, sql_query=self.sql_query, user=self.user,
                                         project_path=project, job_specifier=job_specifier)

    def get_project_size(self):
        """
        Get the size of the project in MegaByte.

        Returns:
            float: project size
        """
        folder_size = sum([sum([os.path.getsize(os.path.join(path, file)) for file in files]) for (path, dirs, files) in
                           os.walk(self.path)])
        return folder_size / (1024 * 1024.0)

    def groups(self):
        """
        Filter project by groups

        Returns:
            Project: a project which is filtered by groups
        """
        new = self.copy()
        new._filter = ["groups"]
        return new

    def inspect(self, job_specifier):
        """
        Inspect an existing pyiron object - most commonly a job - from the database

        Args:
            job_specifier (str, int): name of the job or job ID

        Returns:
            JobCore: Access to the HDF5 object - not a GenericJob object - use load() instead.
        """
        return self.load(job_specifier=job_specifier, convert_to_object=False)

    def iter_jobs(self, path=None, recursive=True, convert_to_object=True):
        """
        Iterate over the jobs within the current project and it is sub projects

        Args:
            path (str): HDF5 path inside each job object
            recursive (bool): search subprojects [True/False] - True by default
            convert_to_object (bool): load the full GenericJob object (default) or just the HDF5 / JobCore object

        Returns:
            yield: Yield of GenericJob or JobCore
        """
        if path is not None:
            for job_id in self.get_jobs(recursive)["id"]:
                yield self.load(job_id, convert_to_object=False)[path]
        else:  # Backwards compatibility - in future the option convert_to_object should be removed
            for job_id in self.get_jobs(recursive)["id"]:
                yield self.load(job_id, convert_to_object=convert_to_object)

    def iter_output(self, recursive=True):
        """
        Iterate over the output of jobs within the current project and it is sub projects

        Args:
            recursive (bool): search subprojects [True/False] - True by default

        Returns:
            yield: Yield of GenericJob or JobCore
        """
        return self.iter_jobs(path='output', recursive=recursive)

    def iter_groups(self):
        """
        Iterate over the groups within the current project

        Returns:
            yield: Yield of sub projects/ groups/ folders
        """
        for group in self.list_groups():
            yield self[group]

    def items(self):
        """
        All items in the current project - this includes jobs, sub projects/ groups/ folders and any kind of files

        Returns:
            list: items in the project
        """
        return [(key, self[key]) for key in self.keys()]

    def job_table(self, recursive=True, columns=["job", "project", "chemicalformula"], all_columns=True, sort_by="id",
                  element_lst=None):
        """
        Access the job_table

        Args:
            recursive (bool): search subprojects [True/False] - default=True
            columns (list): by default only the columns ['job', 'project', 'chemicalformula'] are selected, but the
                            user can select a subset of ['id', 'status', 'chemicalformula', 'job', 'subjob', 'project',
                            'projectpath', 'timestart', 'timestop', 'totalcputime', 'computer', 'hamilton', 'hamversion',
                            'parentid', 'masterid']
            all_columns (bool): Select all columns - this overwrites the columns option.
            sort_by (str): Sort by a specific column
            element_lst (list): list of elements required in the chemical formular - by default None

        Returns:
            pandas.Dataframe: Return the result as a pandas.Dataframe object
        """
        return job_table(database=self.db, sql_query=self.sql_query, user=self.user, project_path=self.project_path,
                         recursive=recursive, columns=columns, all_columns=all_columns, sort_by=sort_by,
                         element_lst=element_lst)

    def keys(self):
        """
        List of file-, folder- and objectnames

        Returns:
            list: list of the names of project directories and project nodes
        """
        return self.list_dirs() + self.list_nodes()

    def list_all(self):
        """
        Combination of list_groups(), list_nodes() and list_files() all in one dictionary with the corresponding keys:
        - 'groups': Subprojects/ -folder/ -groups.
        - 'nodes': Jobs or pyiron objects
        - 'files': Files inside a project which do not belong to any pyiron object

        Returns:
            dict: dictionary with all items in the project
        """
        return {'groups': self.list_groups(), 'nodes': self.list_nodes(), 'files': self.list_files()}

    def list_dirs(self, skip_hdf5=True):
        """
        List directories inside the project

        Args:
            skip_hdf5 (bool): Skip directories which belong to a pyiron object/ pyiron job - default=True

        Returns:
            list: list of directory names
        """
        if "groups" not in self._filter:
            return []
        files = set(next(os.walk(self.path))[2])
        dirs = set(os.listdir(self.path)) - files
        dirs = sorted([direct for direct in dirs if not (direct[0] == ".")])
        if skip_hdf5:
            return [d for d in dirs if not self._is_hdf5_dir(d)]
        return dirs

    def list_files(self, extension=None):
        """
        List files inside the project

        Args:
            extension (str): filter by a specific extension

        Returns:
            list: list of file names
        """
        if "nodes" not in self._filter:
            return []
        try:
            files = next(os.walk(self.path))[2]
            if extension is None:
                return files
            return [".".join(f.split(".")[:-1]) for f in files if f.split(".")[-1] in extension]
        except StopIteration:
            return []

    def list_groups(self):
        """
        List directories inside the project

        Returns:
            list: list of directory names
        """
        return self.list_dirs()

    def list_nodes(self, recursive=False):
        """
        List nodes/ jobs/ pyiron objects inside the project

        Args:
            recursive (bool): search subprojects [True/False] - default=False

        Returns:
            dict: columns are used as keys and point to a list of the corresponding values
        """
        if "nodes" not in self._filter:
            return []
        return self.get_jobs(recursive=recursive, columns=["job"])["job"]

    def load(self, job_specifier, convert_to_object=True):
        """
        Load an existing pyiron object - most commonly a job - from the database

        Args:
            job_specifier (str, int): name of the job or job ID
            convert_to_object (bool): convert the object to an pyiron object or only access the HDF5 file - default=True
                                      accessing only the HDF5 file is about an order of magnitude faster, but only
                                      provides limited functionality. Compare the GenericJob object to JobCore object.

        Returns:
            GenericJob, JobCore: Either the full GenericJob object or just a reduced JobCore object
        """
        if self.sql_query is not None:
            s.logger.warn('SQL filter \'%s\' is active (may exclude job) ', self.sql_query)
        job_id = self.get_job_id(job_specifier=job_specifier)
        if job_id is None:
            s.logger.warn('Job \'%s\' does not exist and cannot be loaded', job_specifier)
            return None
        return self.load_from_jobpath(job_id=job_id, convert_to_object=convert_to_object)

    def load_from_jobpath(self, job_id=None, db_entry=None, convert_to_object=True):
        """
        Internal function to load an existing job either based on the job ID or based on the database entry dictionary.
        
        Args:
            job_id (int): Job ID - optional, but either the job_id or the db_entry is required.
            db_entry (dict): database entry dictionary - optional, but either the job_id or the db_entry is required.
            convert_to_object (bool): convert the object to an pyiron object or only access the HDF5 file - default=True
                                      accessing only the HDF5 file is about an order of magnitude faster, but only
                                      provides limited functionality. Compare the GenericJob object to JobCore object.

        Returns:
            GenericJob, JobCore: Either the full GenericJob object or just a reduced JobCore object
        """
        from pyiron_base.objects.job.path import JobPath
        if job_id:
            job = JobPath(db=self.db, job_id=job_id, user=self.user)
            job = job.load_object(convert_to_object=convert_to_object, project=job.project_hdf5.copy())
            return job
        elif db_entry:
            job = JobPath(db=self.db, db_entry=db_entry)
            job = job.load_object(convert_to_object=convert_to_object, project=job.project_hdf5.copy())
            return job
        else:
            raise ValueError('Either a job ID or an database entry has to be provided.')

    def move_to(self, destination):
        """
        Similar to the copy_to() function move the project object to a different pyiron path - including the content of
        the project (all jobs).

        Args:
            destination (Project): project path to move the project content to

        Returns:
            Project: pointing to the new project path
        """
        if not self.view_mode:
            if not isinstance(destination, Project):
                raise TypeError('A project can only be copied to another project.')
            for sub_project_name in self.list_groups():
                if "_hdf5" not in sub_project_name:
                    sub_project = self.open(sub_project_name)
                    destination_sub_project = destination.open(sub_project_name)
                    sub_project.move_to(destination_sub_project)
            for job_id in self.get_job_ids(recursive=False):
                ham = self.load(job_id)
                ham.move_to(destination)
            for file in self.list_files():
                shutil.move(os.path.join(self.path, file), destination.path)
        else:
            raise EnvironmentError('move_to: is not available in Viewermode !')

    def nodes(self):
        """
        Filter project by nodes

        Returns:
            Project: a project which is filtered by nodes
        """
        new = self.copy()
        new._filter = ["nodes"]
        return new

    def queue_table(self, project_only=True, recursive=True):
        """
        Display the queuing system table as pandas.Dataframe

        Args:
            project_only (bool): Query only for jobs within the current project - True by default
            recursive (bool): Include jobs from sub projects

        Returns:
            pandas.DataFrame: Output from the queuing system - optimized for the Sun grid engine
        """
        return queue_table(job_ids=self.get_job_ids(recursive=recursive), project_only=project_only)

    def refresh_job_status_based_on_queue_status(self, job_specifier, status='running'):
        """
        Check if the job is still listed as running, while it is no longer listed in the queue.

        Args:
            job_specifier (str, int): name of the job or job ID
            status (str): Currently only the jobstatus of 'running' jobs can be refreshed - default='running'
        """
        if status != 'running':
            raise NotImplementedError()
        job_id = get_job_id(database=self.db, sql_query=self.sql_query, user=self.user,
                            project_path=self.project_path, job_specifier=job_specifier)
        self.refresh_job_status_based_on_job_id(job_id)

    def refresh_job_status_based_on_job_id(self, job_id, que_mode=True):
        """
        Internal function to check if a job is still listed 'running' in the job_table while it is no longer listed in
        the queuing system. In this case update the entry in the job_table to 'aborted'.

        Args:
            job_id (int): job ID
            que_mode (bool): [True/False] - default=True
        """
        if job_id:
            if (not que_mode and self.db.get_item_by_id(job_id)['status'] not in ['finished']) or (
                        que_mode and self.db.get_item_by_id(job_id)['status'] in ['running', 'submitted']):
                try:
                    queue_status = queue_id_table(job_id)
                except Exception:
                    queue_status = None
                if queue_status:
                    for key, (q_id, q_status) in queue_status.items():
                        if q_status != 'r':
                            self.db.item_update({'status': 'aborted'}, job_id)
                else:
                    self.db.item_update({'status': 'aborted'}, job_id)

    def remove_file(self, file_name):
        """
        Remove a file (same as unlink()) - copied from os.remove()

        If dir_fd is not None, it should be a file descriptor open to a directory,
          and path should be relative; path will then be relative to that directory.
        dir_fd may not be implemented on your platform.
          If it is unavailable, using it will raise a NotImplementedError.

        Args:
            file_name (str): name of the file
        """
        if not self.view_mode:
            os.remove(posixpath.join(self.path, file_name))
        else:
            raise EnvironmentError('copy_to: is not available in Viewermode !')

    def remove_job(self, job_specifier, _unprotect=False):
        """
        Remove a single job from the project based on its job_specifier - see also remove_jobs()
        
        Args:
            job_specifier (str, int): name of the job or job ID
            _unprotect (bool): [True/False] delete the job without validating the dependencies to other jobs
                               - default=False
        """
        if not self.view_mode:
            try:
                job = self.load(job_specifier=job_specifier, convert_to_object=False)
                if job is None:
                    s.logger.warn('Job \'%s\' does not exist and could not be removed', str(job_specifier))
                elif _unprotect:
                    job.remove_child()
                else:
                    job.remove()
            except IOError as _:
                s.logger.debug('hdf file does not exist. Removal from database will be attempted.')
                job_id = self.get_job_id(job_specifier)
                self.db.delete_item(job_id)
        else:
            raise EnvironmentError('copy_to: is not available in Viewermode !')

    def remove_jobs(self, recursive=False):
        """
        Remove all jobs in the current project and in all subprojects if recursive=True is selected - see also remove_job()

        Args:
            recursive (bool): [True/False] delete all jobs in all subprojects - default=False
        """
        if not self.view_mode:
            for job_id in self.get_job_ids(recursive=recursive):
                if job_id not in self.get_job_ids(recursive=recursive):
                    continue
                else:
                    try:
                        self.remove_job(job_specifier=job_id)
                        s.logger.debug("Remove job with ID {0} ".format(job_id))
                    except (IndexError, Exception):
                        s.logger.debug("Could not remove job with ID {0} ".format(job_id))
        else:
            raise EnvironmentError('copy_to: is not available in Viewermode !')

    def remove(self, enforce=False):
        """
        Delete all the whole project including all jobs in the project and its subprojects

        Args:
            enforce (bool): [True/False] delete jobs even though they are used in other projects - default=False
        """
        if not self.view_mode:
            for sub_project_name in self.list_groups():
                if "_hdf5" not in sub_project_name:
                    sub_project = self.open(sub_project_name)
                    sub_project.remove(enforce=enforce)
            self.remove_jobs(recursive=True)
            for file in self.list_files():
                os.remove(os.path.join(self.path, file))
            if enforce:
                print('remove directory: {}'.format(self.path))
                shutil.rmtree(self.path, ignore_errors=True)
            else:
                self.parent_group.removedirs(self.base_name)
        else:
            raise EnvironmentError('copy_to: is not available in Viewermode !')

    def set_job_status(self, job_specifier, status, project=None):
        """
        Set the status of a particular job

        Args:
            job_specifier (str): name of the job or job ID
            status (str): job status can be one of the following ['initialized', 'appended', 'created', 'submitted',
                         'running', 'aborted', 'collect', 'suspended', 'refresh', 'busy', 'finished']

        """
        if not project:
            project = self.project_path
        return set_job_status(database=self.db, sql_query=self.sql_query, user=self.user, project_path=project,
                              job_specifier=job_specifier, status=status)

    def values(self):
        """
        All items in the current project - this includes jobs, sub projects/ groups/ folders and any kind of files

        Returns:
            list: items in the project
        """
        return [self[key] for key in self.keys()]

    def switch_to_viewer_mode(self):
        """
        Switch from user mode to viewer mode - if viewer_mode is enable pyiron has read only access to the database.
        """
        s.switch_to_viewer_mode()
        db_name = s.top_path_dict[self.root_path]
        s.open_connection()
        self.db = s.db_dict[db_name]

    def switch_to_user_mode(self):
        """
        Switch from viewer mode to user mode - if viewer_mode is enable pyiron has read only access to the database.
        """
        s.switch_to_user_mode()
        db_name = s.top_path_dict[self.root_path]
        s.open_connection()
        self.db = s.db_dict[db_name]

    def queue_delete_job(self, item):
        """
        Delete a job from the queuing system

        Args:
            item (int, GenericJob): Provide either the job_ID or the full hamiltonian

        Returns:
            str: Output from the queuing system as string - optimized for the Sun grid engine
        """
        if isinstance(item, int):
            self.remove_job(job_specifier=item)
        else:
            item.remove()

    @staticmethod
    def create_hdf(path, job_name):
        """
        Create an ProjectHDFio object to store project related information - for example aggregated data

        Args:
            path (str): absolute path
            job_name (str): name of the HDF5 container

        Returns:
            ProjectHDFio: HDF5 object
        """
        return ProjectHDFio(project=Project(path), file_name=job_name, h5_path='/' + job_name)

    @staticmethod
    def queue_is_empty():
        """
        Check if the queue table is currently empty - no more jobs to wait for.

        Returns:
            bool: True if the table is empty, else False - optimized for the Sun grid engine
        """
        return queue_is_empty()

    @staticmethod
    def queue_enable_reservation(item):
        """
        Enable a reservation for a particular job within the queuing system

        Args:
            item (int, GenericJob): Provide either the job_ID or the full hamiltonian

        Returns:
            str: Output from the queuing system as string - optimized for the Sun grid engine
        """
        return queue_enable_reservation(item)

    @staticmethod
    def queue_job_info(item):
        """
        Short reporting for a particular job - using the qstat command of the sun grid engine.

        Args:
            item (int, GenericJob): Provide either the job_ID or the full hamiltonian

        Returns:
            pandas.DataFrame: Short report returned from the queuing system - optimized for the Sun grid engine
        """
        return queue_job_info(item)

    @staticmethod
    def queue_report(item):
        """
        Detailed reporting for a particular job - using the qacct command of the sun grid engine.

        Args:
            item (int, GenericJob): Provide either the job_ID or the full hamiltonian

        Returns:
            pandas.DataFrame: Detailed report returned from the queuing system - optimized for the Sun grid engine
        """
        return queue_report(item)

    @staticmethod
    def wait_for_job(job, interval_in_s=5, max_iterations=100):
        """
        Sleep until the job is finished but maximum interval_in_s * max_iterations seconds.

        Args:
            job (GenericJob): Job to wait for
            interval_in_s (int): interval when the job status is queried from the database - default 5 sec.
            max_iterations (int): maximum number of iterations - default 100
        """
        wait_for_job(job=job, interval_in_s=interval_in_s, max_iterations=max_iterations)

    @staticmethod
    def set_logging_level(level, channel=None):
        """
        Set level for logger

        Args:
            level (str): 'DEBUG, INFO, WARN'
            channel (int): 0: file_log, 1: stream, None: both
        """
        set_logging_level(level=level, channel=channel)

    def __getitem__(self, item):
        """
        Get item from project

        Args:
            item (str, int): key

        Returns:
            Project, GenericJob, JobCore, dict, list, float: basically any kind of item inside the project.
        """
        if isinstance(item, slice):
            if not (item.start or item.stop or item.step):
                return self.values()
            print("slice: ", item)
            raise NotImplementedError("Implement if needed, e.g. for [:]")
        else:
            item_lst = item.split("/")
            if len(item_lst) > 1:
                return self._get_item_helper(item=item_lst[0],
                                             convert_to_object=False).__getitem__("/".join(item_lst[1:]))
        return self._get_item_helper(item=item, convert_to_object=True)

    def _get_item_helper(self, item, convert_to_object=True):
        """
        Internal helper function to get item from project

        Args:
            item (str, int): key
            convert_to_object (bool): convert the object to an pyiron object or only access the HDF5 file - default=True
                                      accessing only the HDF5 file is about an order of magnitude faster, but only
                                      provides limited functionality. Compare the GenericJob object to JobCore object.

        Returns:
            Project, GenericJob, JobCore, dict, list, float: basically any kind of item inside the project.
        """
        if item == "..":
            return self.parent_group
        if item in self.list_nodes():
            if self._inspect_mode or not convert_to_object:
                return self.inspect(item)
            return self.load(item)
        if item in self.list_files(extension="h5"):
            file_name = posixpath.join(self.path, "{}.h5".format(item))
            return ProjectHDFio(project=self, file_name=file_name)
        if item in self.list_files():
            file_name = posixpath.join(self.path, "{}".format(item))
            with open(file_name) as f:
                return f.readlines()
        if item in self.list_dirs():
            with self.open(item) as new_item:
                return new_item.copy()
        raise ValueError("Unknown item: {}".format(item))

    def __repr__(self):
        """
        Human readable string representation of the project object

        Returns:
            str: string representation
        """
        groups = self.list_dirs(skip_hdf5=True)
        nodes = self.list_nodes()
        return str(groups + nodes)

    def __setitem__(self, key, value):
        """
        Store data in the ProjectStore container

        Args:
            key (str): key within the container
            value (dict, list, float, int): data to store
        """
        if self._store is None:
            where_dict = {'job': 'ProjectStore', 'project': str(self.project_path), 'subjob': '/ProjectStore'}
            store_job_id = self.db.get_items_dict(where_dict)['id']
            if store_job_id:
                self._store = self.load(store_job_id)
            else:
                self._store = self.create_job('ProjectStore', 'ProjectStore')
        self._store[key] = value

    @staticmethod
    def _is_hdf5_dir(item):
        """
        Static internal function to check if the current project directory belongs to an pyiron object

        Args:
            item (str): folder/ project name

        Returns:
            bool: [True/False]
        """
        it = item.split('_')
        if len(it) > 1:
            if 'hdf5' in it[-1]:
                return True
        return False

    def _remove_files(self, pattern='*'):
        """
        Remove files within the current project

        Args:
            pattern (str): glob pattern - default="*"
        """
        if not self.view_mode:
            import glob
            pattern = posixpath.join(self.path, pattern)
            for f in glob.glob(pattern):
                s.logger.info('remove file {}'.format(posixpath.basename(f)))
                os.remove(f)
        else:
            raise EnvironmentError('copy_to: is not available in Viewermode !')

    def _queue_delete_job(self, item):
        """
        Delete a job from the queuing system

        Args:
            item (int, GenericJob): Provide either the job_ID or the full hamiltonian

        Returns:
            str: Output from the queuing system as string - optimized for the Sun grid engine
        """
        if not self.view_mode:
            return queue_delete_job(item)
        else:
            raise EnvironmentError('copy_to: is not available in Viewermode !')

    def _update_jobs_in_old_database_format(self, job_name):
        """

        Args:
            job_name (str):
        """
        db_entry_in_old_format = self.db.get_items_dict({'job': job_name, 'project': self.project_path[:-1]})
        if db_entry_in_old_format and len(db_entry_in_old_format) == 1:
            self.db.item_update({'project': self.project_path}, db_entry_in_old_format[0]['id'])
        elif db_entry_in_old_format:
            for entry in db_entry_in_old_format:
                self.db.item_update({'project': self.project_path}, entry['id'])
