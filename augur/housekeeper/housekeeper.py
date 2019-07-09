import logging
import requests
from multiprocessing import Process, Queue
import time
import sqlalchemy as s
import pandas as pd
import os
import zmq
logging.basicConfig(filename='housekeeper.log')

class Housekeeper:

    def __init__(self, jobs, broker, broker_port, user, password, host, port, dbname):

        self.broker_port = broker_port
        self.broker = broker
        DB_STR = 'postgresql://{}:{}@{}:{}/{}'.format(
            user, password, host, port, dbname
        )

        dbschema='augur_data'
        self.db = s.create_engine(DB_STR, poolclass=s.pool.NullPool,
            connect_args={'options': '-csearch_path={}'.format(dbschema)})

        helper_schema = 'augur_operations'
        self.helper_db = s.create_engine(DB_STR, poolclass = s.pool.NullPool,
            connect_args={'options': '-csearch_path={}'.format(helper_schema)})

        repoUrlSQL = s.sql.text("""
            SELECT repo_git FROM repo
        """)

        rs = pd.read_sql(repoUrlSQL, self.db, params={})

        all_repos = rs['repo_git'].values.tolist()

        # List of tasks that need periodic updates
        self.__updatable = self.sort_issue_repos(jobs)

        self.__processes = []
        # logging.info("HK pid: {}".format(str(os.getpid())))
        self.__updater()

    @staticmethod
    def updater_process(broker_port, broker, model, delay, repos, repo_group_id):
        """
        Controls a given plugin's update process
        :param name: name of object to be updated 
        :param delay: time needed to update
        :param shared: shared object that is to also be updated
        """
        logging.info('Housekeeper spawned {} model updater process for subsection {} with PID {}'.format(model, repo_group_id, os.getpid()))
        try:
            # Waiting for 1 alive worker
            while True:
                if broker is not None:
                    if len(broker._getvalue().keys()) > 1:
                        logging.info("Housekeeper recognized that the broker has at least one worker... beginning to distribute maintained tasks")
                        time.sleep(10)
                        while True:
                            logging.info('Housekeeper updating {} model for subsection: {}...'.format(model, repo_group_id))
                            
                            for repo in repos:
                                task = {
                                    "job_type": "MAINTAIN", 
                                    "models": [model], 
                                    "given": {
                                        "git_url": repo['repo_git']
                                    }
                                }
                                if "focused_task" in repo:
                                    task["focused_task"] = repo['focused_task']
                                try:
                                    requests.post('http://localhost:{}/api/unstable/task'.format(
                                        broker_port), json=task, timeout=10)
                                except Exception as e:
                                    logging.info(str(e))

                                time.sleep(0.5)
                            logging.info("Housekeeper finished sending {} tasks to the broker for it to distribute to your worker(s)".format(str(len(repos))))
                            time.sleep(delay)
                        break
                time.sleep(3)
                
        except KeyboardInterrupt:
            os.kill(os.getpid(), 9)
            os._exit(0)
        except:
            raise

    def __updater(self, updates=None):
        """
        Starts update processes
        """
        logging.info("Starting update processes...")
        if updates is None:
            updates = self.__updatable
        for update in updates:
            up = Process(target=self.updater_process, args=(self.broker_port, self.broker, update['model'], 
                update['delay'], update['repos'], update['repo_group_id']), daemon=True)
            up.start()
            self.__processes.append(up)

    def update_all(self):
        """
        Updates all plugins
        """
        for updatable in self.__updatable:
            updatable['update']()

    def schedule_updates(self):
        """
        Schedules updates
        """
        # don't use this, 
        logging.debug('Scheduling updates...')
        self.__updater()

    def join_updates(self):
        """
        Join to the update processes
        """
        for process in self.__processes:
            process.join()

    def shutdown_updates(self):
        """
        Ends all running update processes
        """
        for process in self.__processes:
            process.terminate()

    def sort_issue_repos(self, jobs):

        for job in jobs:

            # Query all repos and last repo id
            repoUrlSQL = s.sql.text("""
                    SELECT repo_git, repo_id FROM repo WHERE repo_group_id = {} ORDER BY repo_id ASC
                """.format(job['repo_group_id']))

            rs = pd.read_sql(repoUrlSQL, self.db, params={})
            print(len(rs))
            if len(rs) == 0:
                logging.info("Trying to send tasks for repo group with id: {}, but the repo group does not contain any repos".format(job['repo_group_id']))
                continue

            repoIdSQL = s.sql.text("""
                    SELECT since_id_str FROM gh_worker_job
                """)

            job_df = pd.read_sql(repoIdSQL, self.helper_db, params={})

            last_id = int(job_df.iloc[0]['since_id_str'])

            jobHistorySQL = s.sql.text("""
                    SELECT max(history_id) AS history_id, status FROM gh_worker_history
                    GROUP BY status
                    LIMIT 1
                """)

            history_df = pd.read_sql(jobHistorySQL, self.helper_db, params={})

            finishing_task = False
            if len(history_df.index) != 0:
                if history_df.iloc[0]['status'] == 'Stopped':
                    self.history_id = int(history_df.iloc[0]['history_id'])
                    finishing_task = True
                    last_id += 1 #update to match history tuple val rather than just increment
                

            # Rearrange repos so the one after the last one that 
            #   was completed will be ran first
            before_repos = rs.loc[rs['repo_id'].astype(int) < last_id]
            after_repos = rs.loc[rs['repo_id'].astype(int) >= last_id]

            reorganized_repos = after_repos.append(before_repos)

            reorganized_repos['focused_task'] = 1
            reorganized_repos = reorganized_repos.to_dict('records')
            
            if finishing_task:
                reorganized_repos[0]['focused_task'] = 1
            job['repos'] = reorganized_repos
        return jobs

