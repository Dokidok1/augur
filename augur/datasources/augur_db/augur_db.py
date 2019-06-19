#SPDX-License-Identifier: MIT
"""
Data source that uses the Augur relational database of GitHub activity.
"""

import pandas as pd
import sqlalchemy as s
import numpy as np
import re
import datetime
from augur import logger
from augur.util import annotate
import base64

class Augur(object):
    """Uses the Augur database to return dataframes with interesting GitHub indicators"""

    def __init__(self, user, password, host, port, dbname, schema, projects=None):
        """
        Connect to Augur

        :param dbstr: The [database string](http://docs.sqlalchemy.org/en/latest/core/engines.html) to connect to the Augur database
        """
        self.DB_STR = 'postgresql://{}:{}@{}:{}/{}'.format(
            user, password, host, port, dbname
        )

        self.db = s.create_engine(self.DB_STR, poolclass=s.pool.NullPool,
            connect_args={'options': '-csearch_path={}'.format(schema)})

        logger.debug('Augur DB: Connecting to {} schema of {}:{}/{} as {}'.format(schema, host, port, dbname, user))

        self.projects = projects
        # try:
        #     self.userid('howderek')
        # except Exception as e:
        #     logger.error("Could not connect to GHTorrent database. Error: " + str(e))

    def client_git_url_task(identity):
        """Basic request-reply client using REQ socket."""
        socket = zmq.Context().socket(zmq.REQ)
        socket.identity = u"git-url-client-{}".format(identity).encode("ascii")
        socket.connect("ipc://frontend.ipc")

        # Send request, get reply
        request = b'UPDATE {"models":["messages"],"given":{"git_url":"https://github.com/rails/rails.git"}}'
        #logger.info(f'{socket.identity.decode("ascii")}: sending {request.decode("ascii")}')
        socket.send(request)
        reply = socket.recv()
        #logger.info("{}: {}".format(socket.identity.decode("ascii"), reply.decode("ascii")))

    def client_owner_repo_task(identity):
        """Basic request-reply client using REQ socket."""
        socket = zmq.Context().socket(zmq.REQ)
        socket.identity = u"owner-repo-client-{}".format(identity).encode("ascii")
        socket.connect("ipc://frontend.ipc")

        # Send request, get reply
        request = b'UPDATE {"models":["messages"],"given":{"owner_repo_pair":"rails/rails"}}'
        #logger.info(f'{socket.identity.decode("ascii")}: sending {request.decode("ascii")}')
        socket.send(request)
        reply = socket.recv()
    #logger.info("{}: {}".format(socket.identity.decode("ascii"), reply.decode("ascii")))

    #####################################
    ###           EVOLUTION           ###
    #####################################

    @annotate(tag='code-changes')
    def code_changes(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """
        Returns a timeseries of the count of code commits.

        :param repo_group_id: The repository's repo_group_id
        :param repo_id: The repository's repo_id, defaults to None
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of commits/period
        """
        if not begin_date:
            begin_date = '1970-1-1 00:00:00:00'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        code_changes_SQL = ''

        if not repo_id:
            code_changes_SQL = s.sql.text("""
                SELECT
                    date_trunc(:period, cmt_committer_date::DATE) as commit_date,
                    repo_id,
                    COUNT(cmt_commit_hash) as commit_count
                FROM commits
                WHERE repo_id IN (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id)
                AND cmt_committer_date BETWEEN :begin_date AND :end_date
                GROUP BY commit_date, repo_id
                ORDER BY repo_id, commit_date
            """)

            results = pd.read_sql(code_changes_SQL, self.db, params={'repo_group_id': repo_group_id, 'period': period,
                                                                     'begin_date': begin_date, 'end_date': end_date})
            return results

        else:
            code_changes_SQL = s.sql.text("""
                SELECT
                    date_trunc(:period, cmt_committer_date::DATE) as commit_date,
                    COUNT(cmt_commit_hash) as commit_count
                FROM commits
                WHERE repo_id = :repo_id
                AND cmt_committer_date BETWEEN :begin_date AND :end_date
                GROUP BY commit_date
                ORDER BY commit_date
            """)

            results = pd.read_sql(code_changes_SQL, self.db, params={'repo_id': repo_id, 'period': period,
                                                                     'begin_date': begin_date, 'end_date': end_date})
            return results


    @annotate(tag='pull-requests-merge-contributor-new')
    def pull_requests_merge_contributor_new(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """
        Returns a timeseries of the count of persons contributing with an accepted commit for the first time.

        :param repo_id: The repository's id
        :param repo_group_id: The repository's group id
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of persons/period
        """
        if not begin_date:
            begin_date = '1970-1-1 00:00:01'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if repo_id:
            commitNewContributor = s.sql.text("""
                SELECT date_trunc(:period, new_date::DATE) as commit_date, 
                COUNT(cmt_author_email)
                FROM ( SELECT cmt_author_email, MIN(TO_TIMESTAMP(cmt_author_date,'YYYY-MM-DD')) AS new_date
                FROM commits WHERE
                repo_id = :repo_id 
                AND TO_TIMESTAMP(cmt_author_date,'YYYY-MM-DD') BETWEEN :begin_date AND :end_date AND cmt_author_email IS NOT NULL
                GROUP BY cmt_author_email
                ) as abc GROUP BY commit_date
            """)
            results = pd.read_sql(commitNewContributor, self.db, params={'repo_id': repo_id, 'period': period,
                                                                         'begin_date': begin_date,
                                                                         'end_date': end_date})
        else:
            commitNewContributor = s.sql.text("""
                SELECT date_trunc(:period, new_date::DATE) as commit_date, 
                COUNT(cmt_author_email)
                FROM ( SELECT cmt_author_email, MIN(TO_TIMESTAMP(cmt_author_date,'YYYY-MM-DD')) AS new_date
                FROM commits WHERE
                repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id) 
                AND TO_TIMESTAMP(cmt_author_date,'YYYY-MM-DD') BETWEEN :begin_date AND :end_date AND cmt_author_email IS NOT NULL
                GROUP BY cmt_author_email
                ) as abc GROUP BY commit_date
            """)
            results = pd.read_sql(commitNewContributor, self.db,
                                  params={'repo_group_id': repo_group_id, 'period': period,
                                          'begin_date': begin_date,
                                          'end_date': end_date})
        return results

    @annotate(tag='issues-first-time-opened')
    def issues_first_time_opened(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """
        Returns a timeseries of the count of persons opening an issue for the first time.

        :param repo_id: The repository's id
        :param repo_group_id: The repository's group id
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of persons/period
        """

        if not begin_date:
            begin_date = '1970-1-1 00:00:01'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if repo_id:
            issueNewContributor = s.sql.text("""
                SELECT
                    date_trunc(:period, new_date::DATE) as issue_date,
                    COUNT(gh_user_id)
                FROM (
                    SELECT
                        gh_user_id,
                        MIN(created_at) AS new_date
                    FROM
                        issues
                    WHERE
                        repo_id = :repo_id
                        AND created_at BETWEEN :begin_date AND :end_date
                    GROUP BY gh_user_id
                ) as abc
                GROUP BY issue_date
                ORDER BY issue_date
            """)
            results = pd.read_sql(issueNewContributor, self.db, params={'repo_id': repo_id, 'period': period,
                                                                        'begin_date': begin_date, 'end_date': end_date})
        else:
            issueNewContributor = s.sql.text("""
                SELECT
                    date_trunc(:period, new_date::DATE) as issue_date,
                    COUNT(gh_user_id)
                FROM (
                    SELECT
                        gh_user_id,
                        MIN(created_at) AS new_date
                    FROM
                        issues
                    WHERE
                        repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id) 
                        AND created_at BETWEEN :begin_date AND :end_date
                    GROUP BY gh_user_id
                ) as abc
                GROUP BY issue_date
                ORDER BY issue_date
            """)
            results = pd.read_sql(issueNewContributor, self.db,
                                  params={'repo_group_id': repo_group_id, 'period': period,
                                          'begin_date': begin_date, 'end_date': end_date})
        return results

    @annotate(tag='issues-first-time-closed')
    def issues_first_time_closed(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None, ):
        """
        Returns a timeseries of the count of persons closing an issue for the first time.

        :param repo_id: The repository's id
        :param repo_group_id: The repository's group id
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of persons/period
        """

        if not begin_date:
            begin_date = '1970-1-1 00:00:01'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if repo_id:
            issuesClosedSQL = s.sql.text("""
                SELECT
                    date_trunc(:period, new_date::DATE) AS issue_date, COUNT(cntrb_id)
                FROM (
                    SELECT cntrb_id, MIN(created_at) AS new_date
                    FROM issue_events
                    WHERE
                        issue_id IN 
                        (SELECT issue_id FROM issues 
                        WHERE repo_id = :repo_id)
                        AND action = 'closed'
                    GROUP BY cntrb_id ) AS iss_close
                GROUP BY issue_date
            """)
            results = pd.read_sql(issuesClosedSQL, self.db, params={'repo_id': repo_id, 'period': period,
                                                                    'begin_date': begin_date, 'end_date': end_date})
        else:
            issuesClosedSQL = s.sql.text("""
                 SELECT
                    date_trunc(:period, new_date::DATE) AS issue_date, COUNT(cntrb_id)
                FROM (
                    SELECT cntrb_id, MIN(created_at) AS new_date
                    FROM issue_events
                    WHERE
                        issue_id IN 
                        (SELECT issue_id FROM issues 
                        WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id))
                        AND action = 'closed'
                    GROUP BY cntrb_id ) AS iss_close
                GROUP BY issue_date 
            """)
            results = pd.read_sql(issuesClosedSQL, self.db, params={'repo_group_id': repo_group_id, 'period': period,
                                                                    'begin_date': begin_date, 'end_date': end_date})

        return results

    @annotate(tag='sub-projects')
    def sub_projects(self, repo_group_id, repo_id=None, begin_date=None, end_date=None):
        """
        Returns number of sub-projects
        :param repo_id: The repository's id
        :param repo_group_id: The repository's group id
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        """
        if not begin_date:
            begin_date = '1970-1-1 00:00:01'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if repo_id:
            sub_projectsSQL = s.sql.text("""
                SELECT COUNT(*)  AS sub_protject_count
                FROM repo
                WHERE repo_group_id = (
                SELECT repo_group_id
                FROM repo
                WHERE  repo_id = :repo_id)
                AND repo_added BETWEEN :begin_date AND :end_date
            """)

            results = pd.read_sql(sub_projectsSQL, self.db, params={'repo_id': repo_id,
                                                                    'begin_date': begin_date, 'end_date': end_date})
        else:
            sub_projectsSQL = s.sql.text("""
                SELECT COUNT(*) AS sub_protject_count
                FROM repo
                WHERE repo_group_id = :repo_group_id
                AND repo_added BETWEEN :begin_date AND :end_date
            """)

            results = pd.read_sql(sub_projectsSQL, self.db, params={'repo_group_id': repo_group_id,
                                                                    'begin_date': begin_date, 'end_date': end_date})
        return results

    @annotate(tag='contributors')
    def contributors(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """
        Returns a timeseries of all the contributions to a project.

        DataFrame has these columns:
        date
        commits
        pull_requests
        issues
        commit_comments
        pull_request_comments
        issue_comments
        total

        :param repo_id: The repository's id
        :param repo_group_id: The repository's group id
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of persons/period
        """

        # In this version, pull request, pr request comments,issue comments haven't be calculated
        if not begin_date:
            begin_date = '1970-1-1 00:00:01'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if repo_id:
            contributorsSQL = s.sql.text("""
                SELECT id AS user, SUM(commits) AS commits, SUM(issues) AS issues, SUM(commit_comments) AS commit_comments, 
                SUM(issue_comments) AS issue_comments, SUM(pull_requests) AS pull_requests, 
                SUM(pull_request_comments) AS pull_request_comments,
                SUM(a.commits + a.issues + a.commit_comments + a.issue_comments + a.pull_requests + a.pull_request_comments) AS total
                FROM (
                (SELECT gh_user_id AS id,
                0 AS commits, COUNT(*) AS issues, 0 AS commit_comments, 0 AS issue_comments, 0 AS pull_requests, 0 AS pull_request_comments
                FROM issues
                WHERE repo_id = :repo_id 
                AND created_at BETWEEN :begin_date AND :end_date AND gh_user_id IS NOT NULL 
                GROUP BY gh_user_id)
                UNION ALL 
                (SELECT cmt_ght_author_id AS id,
                COUNT(*) AS commits,  0 AS issues, 0 AS commit_comments, 0 AS issue_comments, 0 AS pull_requests, 0 AS pull_request_comments
                FROM commits
                WHERE repo_id = :repo_id 
                AND cmt_ght_author_id IS NOT NULL AND cmt_committer_date BETWEEN :begin_date AND :end_date
                GROUP BY cmt_ght_author_id)
                UNION ALL
                (SELECT user_id AS id, 0 AS commits, 0 AS issues, COUNT(*) AS commit_comments, 
                0 AS issue_comments, 0 AS pull_requests, 0 AS pull_request_comments
                FROM commit_comment_ref 
                WHERE cmt_id in (SELECT cmt_id FROM commits WHERE repo_id = :repo_id ) 
                AND created_at BETWEEN :begin_date AND :end_date AND user_id IS NOT NULL
                GROUP BY user_id) 
                ) a GROUP BY a.id ORDER BY total DESC
            """)

            results = pd.read_sql(contributorsSQL, self.db, params={'repo_id': repo_id, 'period': period,
                                                                    'begin_date': begin_date, 'end_date': end_date})
        else:
            contributorsSQL = s.sql.text("""
                SELECT id AS user, SUM(commits) AS commits, SUM(issues) AS issues, SUM(commit_comments) AS commit_comments, 
                SUM(issue_comments) AS issue_comments, SUM(pull_requests) AS pull_requests, 
                SUM(pull_request_comments) AS pull_request_comments,
                SUM(a.commits + a.issues + a.commit_comments + a.issue_comments + a.pull_requests + a.pull_request_comments) AS total
                FROM (
                (SELECT gh_user_id AS id,
                0 AS commits, COUNT(*) AS issues, 0 AS commit_comments, 0 AS issue_comments, 0 AS pull_requests, 0 AS pull_request_comments
                FROM issues
                WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id)  
                AND created_at BETWEEN :begin_date AND :end_date AND gh_user_id IS NOT NULL 
                GROUP BY gh_user_id)
                UNION ALL 
                (SELECT cmt_ght_author_id AS id,
                COUNT(*) AS commits,  0 AS issues, 0 AS commit_comments, 0 AS issue_comments, 0 AS pull_requests, 0 AS pull_request_comments
                FROM commits
                WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id) 
                AND cmt_ght_author_id IS NOT NULL AND cmt_committer_date BETWEEN :begin_date AND :end_date
                GROUP BY cmt_ght_author_id)
                UNION ALL
                (SELECT user_id AS id, 0 AS commits, 0 AS issues, COUNT(*) AS commit_comments, 
                0 AS issue_comments, 0 AS pull_requests, 0 AS pull_request_comments
                FROM commit_comment_ref 
                WHERE cmt_id in (SELECT cmt_id FROM commits WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id)) 
                AND created_at BETWEEN :begin_date AND :end_date AND user_id IS NOT NULL
                GROUP BY user_id) 
                ) a GROUP BY a.id ORDER BY total DESC
            """)

            results = pd.read_sql(contributorsSQL, self.db, params={'repo_group_id': repo_group_id, 'period': period,
                                                                    'begin_date': begin_date, 'end_date': end_date})
        return results

    @annotate(tag='contributors-new')
    def contributors_new(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """
        Returns a timeseries of new contributions to a project.

        :param repo_id: The repository's id
        :param repo_group_id: The repository's group id
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of persons/period
        """

        # In this version, pull request, pr request comments,issue comments haven't be calculated
        if not begin_date:
            begin_date = '1970-1-1 00:00:01'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if repo_id:
            contributorsNewSQL = s.sql.text("""
                SELECT date_trunc(:period, created_at::DATE) AS contribute_at, COUNT(id) AS count
                FROM (
                SELECT id as id, MIN(created_at) AS created_at
                FROM (
                (SELECT gh_user_id AS id, MIN(created_at) AS created_at
                FROM issues
                WHERE repo_id = :repo_id
                AND created_at BETWEEN :begin_date AND :end_date AND gh_user_id IS NOT NULL
                GROUP BY gh_user_id)
                UNION ALL
                (SELECT cmt_ght_author_id AS id, MIN(TO_TIMESTAMP(cmt_author_date,'YYYY-MM-DD'))  AS created_at
                FROM commits
                WHERE repo_id = :repo_id
                AND cmt_ght_author_id IS NOT NULL AND TO_TIMESTAMP(cmt_author_date, 'YYYY-MM-DD') BETWEEN :begin_date AND :end_date
                GROUP BY cmt_ght_author_id)
                UNION ALL
                (SELECT user_id AS id, MIN(created_at) AS created_at
                FROM commit_comment_ref
                WHERE cmt_id in (SELECT cmt_id FROM commits WHERE repo_id = :repo_id)
                AND created_at BETWEEN :begin_date AND :end_date AND user_id IS NOT NULL
                GROUP BY user_id)
                UNION ALL
                (SELECT cntrb_id AS id, MIN(created_at) AS created_at
                FROM issue_events
                WHERE issue_id IN (SELECT issue_id FROM issues WHERE repo_id = :repo_id)
                AND created_at BETWEEN :begin_date AND :end_date AND cntrb_id IS NOT NULL
                AND action = 'closed' GROUP BY cntrb_id)
                ) a GROUP BY a.id ) b GROUP BY contribute_at
                """)

            results = pd.read_sql(contributorsNewSQL, self.db, params={'repo_id': repo_id, 'period': period,
                                                                       'begin_date': begin_date, 'end_date': end_date})
        else:
            contributorsNewSQL = s.sql.text("""
                SELECT date_trunc(:period, created_at::DATE) AS contribute_at, COUNT(id) AS count
                FROM (
                SELECT id as id, MIN(created_at) AS created_at
                FROM (
                (SELECT gh_user_id AS id, MIN(created_at) AS created_at
                FROM issues
                WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id)  
                AND created_at BETWEEN :begin_date AND :end_date AND gh_user_id IS NOT NULL
                GROUP BY gh_user_id)
                UNION ALL
                (SELECT cmt_ght_author_id AS id, MIN(TO_TIMESTAMP(cmt_author_date,'YYYY-MM-DD'))  AS created_at
                FROM commits
                WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id) 
                AND cmt_ght_author_id IS NOT NULL AND TO_TIMESTAMP(cmt_author_date, 'YYYY-MM-DD') BETWEEN :begin_date AND :end_date
                GROUP BY cmt_ght_author_id)
                UNION ALL
                (SELECT user_id AS id, MIN(created_at) AS created_at
                FROM commit_comment_ref
                WHERE cmt_id in (SELECT cmt_id FROM commits WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id)) 
                AND created_at BETWEEN :begin_date AND :end_date AND user_id IS NOT NULL
                GROUP BY user_id)
                UNION ALL
                (SELECT cntrb_id AS id, MIN(created_at) AS created_at
                FROM issue_events
                WHERE issue_id IN (SELECT issue_id FROM issues WHERE repo_id in (SELECT repo_id FROM repo WHERE repo_group_id=:repo_group_id))
                AND created_at BETWEEN :begin_date AND :end_date AND cntrb_id IS NOT NULL
                AND action = 'closed' GROUP BY cntrb_id)
                ) a GROUP BY a.id ) b GROUP BY contribute_at
                """)

            results = pd.read_sql(contributorsNewSQL, self.db, params={'repo_group_id': repo_group_id, 'period': period,
                                                                       'begin_date': begin_date, 'end_date': end_date})
        return results

    @annotate(tag='code-changes-lines')
    def code_changes_lines(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """Returns a timeseries of code changes added and removed.

        :param repo_group_id: The repository's repo_group_id
        :param repo_id: The repository's repo_id, defaults to None
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of code changes added and removed/period
        """
        if not begin_date:
            begin_date = '1970-1-1 00:00:00'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        code_changes_lines_SQL = ''

        if not repo_id:
            code_changes_lines_SQL = s.sql.text("""
                SELECT
                    date_trunc(:period, cmt_author_date::DATE) as commit_date,
                    repo_id,
                    SUM(cmt_added) as added,
                    SUM(cmt_removed) as removed
                FROM commits
                WHERE repo_id IN (SELECT repo_id FROM repo WHERE repo_group_id = :repo_group_id)
                AND cmt_author_date BETWEEN :begin_date AND :end_date
                GROUP BY commit_date, repo_id
                ORDER BY repo_id, commit_date
            """)

            results = pd.read_sql(code_changes_lines_SQL, self.db, params={'repo_group_id': repo_group_id, 'period': period,
                                                                           'begin_date': begin_date, 'end_date': end_date})

            return results

        else:
            code_changes_lines_SQL = s.sql.text("""
                SELECT
                    date_trunc(:period, cmt_author_date::DATE) as commit_date,
                    SUM(cmt_added) AS added,
                    SUM(cmt_removed) as removed
                FROM commits
                WHERE repo_id = :repo_id
                AND cmt_author_date BETWEEN :begin_date AND :end_date
                GROUP BY commit_date
                ORDER BY commit_date;
            """)

            results = pd.read_sql(code_changes_lines_SQL, self.db, params={'repo_id': repo_id, 'period': period,
                                                                           'begin_date': begin_date, 'end_date': end_date})
            return results

    @annotate(tag='issues-new')
    def issues_new(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """Returns a timeseries of new issues opened.

        :param repo_group_id: The repository's repo_group_id
        :param repo_id: The repository's repo_id, defaults to None
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of new issues/period
        """
        if not begin_date:
            begin_date = '1970-1-1 00:00:00'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        issues_new_SQL = ''

        if not repo_id:
            issues_new_SQL = s.sql.text("""
                SELECT
                    date_trunc(:period, created_at::DATE) as issue_date,
                    repo_id,
                    COUNT(issue_id) as issues
                FROM issues
                WHERE repo_id IN (SELECT repo_id FROM repo WHERE repo_group_id = :repo_group_id)
                AND created_at BETWEEN to_timestamp(:begin_date, 'YYYY-MM-DD HH24:MI:SS') AND to_timestamp(:end_date, 'YYYY-MM-DD HH24:MI:SS')
                GROUP BY issue_date, repo_id
                ORDER BY repo_id, issue_date
            """)

            results = pd.read_sql(issues_new_SQL, self.db, params={'repo_group_id': repo_group_id, 'period': period,
                                                                   'begin_date': begin_date, 'end_date': end_date})

            return results

        else:
            issues_new_SQL = s.sql.text("""
                SELECT date_trunc(:period, created_at::DATE) as issue_date, COUNT(issue_id) as issues
                FROM issues
                WHERE repo_id = :repo_id
                AND created_at BETWEEN to_timestamp(:begin_date, 'YYYY-MM-DD HH24:MI:SS') AND to_timestamp(:end_date, 'YYYY-MM-DD HH24:MI:SS')
                GROUP BY issue_date
                ORDER BY issue_date;
            """)

            results = pd.read_sql(issues_new_SQL, self.db, params={'repo_id': repo_id, 'period': period,
                                                                   'begin_date': begin_date, 'end_date': end_date})
            return results


    @annotate(tag='issues-closed')
    def issues_closed(self, repo_group_id, repo_id=None, period='day', begin_date=None, end_date=None):
        """Returns a timeseries of issues closed.

        :param repo_group_id: The repository's repo_group_id
        :param repo_id: The repository's repo_id, defaults to None
        :param period: To set the periodicity to 'day', 'week', 'month' or 'year', defaults to 'day'
        :param begin_date: Specifies the begin date, defaults to '1970-1-1 00:00:00'
        :param end_date: Specifies the end date, defaults to datetime.now()
        :return: DataFrame of issues closed/period
        """
        if not begin_date:
            begin_date = '1970-1-1 00:00:00'
        if not end_date:
            end_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if not repo_id:
            issues_closed_SQL = s.sql.text("""
                SELECT
                    date_trunc(:period, closed_at::DATE) as issue_close_date,
                    repo_id,
                    COUNT(issue_id) as issues
                FROM issues
                WHERE repo_id IN (SELECT repo_id FROM repo WHERE repo_group_id = :repo_group_id)
                AND closed_at IS NOT NULL
                AND closed_at BETWEEN to_timestamp(:begin_date, 'YYYY-MM-DD HH24:MI:SS') AND to_timestamp(:end_date, 'YYYY-MM-DD HH24:MI:SS')
                GROUP BY issue_close_date, repo_id
                ORDER BY repo_id, issue_close_date
            """)

            results = pd.read_sql(issues_closed_SQL, self.db, params={'repo_group_id': repo_group_id, 'period': period,
                                                                       'begin_date': begin_date, 'end_date': end_date})

            return results

        else:
            issues_closed_SQL = s.sql.text("""
                SELECT date_trunc(:period, closed_at::DATE) as issue_close_date, COUNT(issue_id) as issues
                FROM issues
                WHERE repo_id = :repo_id
                AND closed_at IS NOT NULL
                AND closed_at BETWEEN to_timestamp(:begin_date, 'YYYY-MM-DD HH24:MI:SS') AND to_timestamp(:end_date, 'YYYY-MM-DD HH24:MI:SS')
                GROUP BY issue_close_date
                ORDER BY issue_close_date;
            """)

            results = pd.read_sql(issues_closed_SQL, self.db, params={'repo_id': repo_id, 'period': period,
                                                                    'begin_date': begin_date, 'end_date': end_date})
            return results

    @annotate(tag='issue-duration')
    def issue_duration(self, repo_url):
        """Returns the duration of each issue.

        :param repo_url: The repository's URL
        :return: DataFrame of issue id with the corresponding duration
        """
        issue_duration_SQL = s.sql.text("""
            SELECT issue_id, (closed_at - created_at) AS duration
            FROM issues
            WHERE repo_id = (SELECT repo_id FROM repo WHERE repo_git LIKE :repourl LIMIT 1)
            AND closed_at IS NOT NULL
            ORDER BY issue_id;
        """)

        results = pd.read_sql(issue_duration_SQL, self.db, params={'repourl': f'%{repo_url}%'})
        return results

    @annotate(tag='issue-backlog')
    def issue_backlog(self, repo_group_id, repo_id=None):
        """Returns number of issues currently open.

        :param repo_group_id: The repository's repo_group_id
        :param repo_id: The repository's repo_id, defaults to None
        :return: DataFrame of count of issues currently open.
        """
        if not repo_id:
            issue_backlog_SQL = s.sql.text("""
                SELECT repo_id, COUNT(issue_id) as issue_backlog
                FROM issues
                WHERE repo_id IN (SELECT repo_id FROM repo WHERE  repo_group_id = :repo_group_id)
                AND issue_state = 'open'
                GROUP BY repo_id
                ORDER BY repo_id
            """)
            result = pd.read_sql(issue_backlog_SQL, self.db, params={'repo_group_id': repo_group_id})
            return result

        else:
            issue_backlog_SQL = s.sql.text("""
                SELECT COUNT(*) as issue_backlog
                FROM issues
                WHERE repo_id = :repo_id
                AND issue_state='open'
            """)

            result = pd.read_sql(issue_backlog_SQL, self.db, params={'repo_id': repo_id})
            return result

    #####################################
    ###         EXPERIMENTAL          ###
    #####################################

    @annotate(tag='lines-changed-by-author')
    def lines_changed_by_author(self, repo_url):
        """
        Returns number of lines changed per author per day

        :param repo_url: the repository's URL
        """
        linesChangedByAuthorSQL = s.sql.text("""
            SELECT cmt_author_email, cmt_author_date, cmt_author_affiliation as affiliation,
                SUM(cmt_added) as additions, SUM(cmt_removed) as deletions, SUM(cmt_whitespace) as whitespace
            FROM commits
            WHERE repo_id = (SELECT repo_id FROM repo WHERE repo_git LIKE :repourl LIMIT 1)
            GROUP BY repo_id, cmt_author_date, cmt_author_affiliation, cmt_author_email
            ORDER BY cmt_author_date ASC;
        """)
        results = pd.read_sql(linesChangedByAuthorSQL, self.db, params={"repourl": '%{}%'.format(repo_url)})
        return results

    @annotate(tag='repo-groups')
    def repo_groups(self):
        """
        Returns number of lines changed per author per day

        :param repo_url: the repository's URL
        """
        repoGroupsSQL = s.sql.text("""
            SELECT *
            FROM repo_groups
        """)
        results = pd.read_sql(repoGroupsSQL, self.db)
        return results

    @annotate(tag='downloaded-repos')
    def downloaded_repos(self):
        """
        Returns all repository names, URLs, and base64 URLs in the facade database
        """
        downloadedReposSQL = s.sql.text("""
            SELECT
                repo.repo_id,
                repo.repo_name,
                repo.description,
                repo.repo_git AS url,
                repo.repo_status,
                a.commits_all_time, 
                b.issues_all_time ,
                rg_name
            FROM
                repo
                left outer join  
                (select repo_id,    COUNT ( commits.cmt_id ) AS commits_all_time from commits group by repo_id ) a on 
                repo.repo_id = a.repo_id
                left outer join  
                (select repo_id, count ( issues.issue_id) as issues_all_time from issues  group by repo_id) b 
                on 
                repo.repo_id = b.repo_id 
                JOIN repo_groups ON repo_groups.repo_group_id = repo.repo_group_id
            order by commits_all_time desc 
        """)
        results = pd.read_sql(downloadedReposSQL, self.db)
        results['url'] = results['url'].apply(lambda datum: datum.split('//')[1])
        # if self.projects:
        #     results = results[results.project_name.isin(self.projects)]
        if self.projects:
              results = results[results.project_name.isin(self.projects)]

        b64_urls = []
        for i in results.index:
            b64_urls.append(base64.b64encode((results.at[i, 'url']).encode()))
        results['base64_url'] = b64_urls

        return results

    @annotate(tag='rg-closed-issues-count')
    def rg_open_issues_count(self, repo_group_id):
        """
        Returns number of lines changed per author per day

        :param repo_url: the repository's URL
        """
        openIssueCountSQL = s.sql.text("""
            SELECT rg_name, count(issue_id) AS open_count, date_trunc('week', issues.created_at) AS DATE
            FROM issues, repo, repo_groups
            WHERE issue_state = 'open'
            AND repo.repo_id = issues.repo_id
            AND repo.repo_group_id = repo_groups.repo_group_id
            GROUP BY date, repo_groups.rg_name
            ORDER BY date
        """)
        results = pd.read_sql(openIssueCountSQL, self.db)#, params={"rg_id": '{}'.format(rg_id)})
        return results

    @annotate(tag='rg-closed-issues-count')
    def rg_closed_issues_count(self, repo_group_id):
        """
        Returns number of lines changed per author per day

        :param repo_url: the repository's URL
        """
        closedIssueCountSQL = s.sql.text("""
            SELECT rg_name, count(issue_id) AS closed_count, date_trunc('week', issues.created_at) AS DATE
            FROM issues, repo, repo_groups
            WHERE issue_state = 'closed'
            AND repo.repo_id = issues.repo_id
            AND repo.repo_group_id = repo_groups.repo_group_id
            GROUP BY date, repo_groups.rg_name
            ORDER BY date
        """)
        results = pd.read_sql(closedIssueCountSQL, self.db)#, params={"rg_id": '{}'.format(rg_id)})
        return results