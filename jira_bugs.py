
Скрипт предназначен для создания багов или же внесение данных в уже существующие баги по accuracy или performance
"""

import pandas as pd
import os
import time
import datetime
import argparse
import sys
import logging
from logging import StreamHandler
from loguru import logger
from jira import JIRA
import urllib3


urllib3.disable_warnings()
# Подавление вывода предупреждений вида default='warn'
pd.options.mode.chained_assignment = None


FORMAT = "{time:YYYY-MM-DD HH:mm:ss} - {level:10} {name}:{function}:{line} - {message}"
logger.add(f'write_bugs_{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log',
          format=FORMAT,
          level="DEBUG")


BUG_VERSION = 'BUG_VERSION'  # Для заполнения поля нового бага с версией BUG_VERSION, в которой обнаружена ошибка
CUR_USER = 'Felis, ServalX' # Необходим только для проверки, когда баг при создании был назначен на его создателя
ASSIGNEE_USER = 'sfelis'
COMP_BY_DEFAULT = 'Validation' 
DEFAULT_FILE = 'accuracy_data_2022-04-05_11-59-06_2022.2.0-7225-8317493e652_reqests.txt'
USER = 'vasha_pochta@pochta.com'
APIKEY = 'dfgnhtbryjtyfjhvdthteybjub'
PASSWORD = 'My_password'
SERVER = 'https://jira.devtools.company.com'
REP_ON = 'Reproduced on'
temp_file = 'tmp.txt'


@logger.catch
def create_parser():
   parser = argparse.ArgumentParser()
   parser.add_argument('--report_file', default=DEFAULT_FILE, type=str, help='Report type must be "accuracy_build_{datetime}_{version}.txt" '
                                                     'or "perf_build_(os_){datetime}_{version}.txt"')
   # parser.add_argument('report_type', type=str, help='Report type must be "acc" or "perf"')
   parser.add_argument('--browser', type=str, default='firefox',
                       help='Working Browsers must be chrome or firefox')
   return parser


@logger.catch
def get_args(parser):
   arguments = parser.parse_args()
   return arguments


@logger.catch
def file_work(name, attr, buf):
   logger.debug(f"*** file_work: attr = {attr}")
   try:
       fl = open(name, attr)
   except OSError as oser:
       logger.error(f"File {name}.txt not created!\n{oser}")
   else:
       if attr != '+' and attr.find('r') == -1 and attr.find('b') == -1:
           fl.write(buf)
   finally:
       fl.close()


@logger.catch
def file_read_params(name, attr, report_type, end_line):
   logger.debug(f"*** file_read_params: attr = {attr}")

   found_model = ''
   found_fw = ''
   found_platform = ''
   found_dev = ''
   found_precision = []
   found_prec = ''
   ver = ''
   short_link = ''
   try:
       with open(name, attr) as tmp:
           lines = tmp.readlines()
   except IOError as oser:
       logging.exception(f"File {name} absent!\n{oser}")
   except FileNotFoundError:
       logging.exception(f"File {name} not found!")
   else:
       for n, line in enumerate(lines):
           # logger.debug(f'************* n, line = {n}, {line} ***')
           if n == 0:
               logger.debug(f'n = {n}, line = {line}')
               ver = line.replace('\n', '')
               logger.debug(f'ver = {ver}')
           if n == 2:
               logger.debug(f'n = {n}, line = {line}')
               short_link = line.replace('\n', '')
               logger.debug(f'short_link = {short_link}')
           if n == 5:
               logger.debug(f'n = {n}, line = {line}')
               found_model = line.split('|')[1]
               found_fw = line.split('|')[2]
               found_platform = line.split('|')[3]

               if report_type == 'acc':
                   found_dev = line.split('|')[5]
                   found_precision.append(line.split('|')[7])
               elif report_type == 'perf':
                   found_dev = line.split('|')[4]
                   found_prec = line.split('|')[6]
                   found_precision.append(found_prec)
           if 5 < n < end_line:
               # logger.debug(f'n = {n}, line = {line}')
               if report_type == 'acc':
                   found_precision.append(line.split('|')[7])
               elif report_type == 'perf':
                   found_precision.append(line.split('|')[6])
           if n > end_line:
               break
   finally:
       tmp.close()
   found_precision.sort()
   # pre_all = ''
   # for el in found_precision:
   #     pre_all += el + ', '
   # pre_all = pre_all[:-2]
   pre_all = found_precision
   logger.debug(f'************* found_precision = {pre_all} ***')
   logger.debug('************* file_read_params END ***')
   return found_model, found_fw, found_platform, found_dev, found_prec, ver, short_link, pre_all


@logger.catch
def temp_file_create(name, text_for_bug):
   try:
       fl = open(name, 'w')
       fl.write(text_for_bug)
   except OSError as oser:
       print(f"File {name} not created!\n{oser}")
   finally:
       fl.close()


@logger.catch
def create_summary(model, fw, platform, dev, precision, report_type):
   logger.debug("*** create_summary")

   summary = ''
   header = "[" + fw + "] " + "[" + model + "]"
   if report_type == 'acc':
       body = ' accuracy deviation on '
   elif report_type == 'perf':
       body = ' performance deviation on '

   tail = "[" + platform + "] " + "[" + dev + "] " + precision
   summary = header + body + tail
   logger.debug(f"summary = {summary}")

   logger.debug('************* create_summary END ***')
   return summary


@logger.catch
def search_in_summary(summary, searching_str):
   summary_low = summary.lower()
   searching_str = searching_str.lower()
   s_str_s = summary_low.find(searching_str)
   s_str_e = -1
   if s_str_s != -1:
       s_str_e = s_str_s + len(searching_str)

   s_symb = ['[', ' ']
   e_symb = [']', ' ', ',']

   if summary_low[s_str_s - 1] in s_symb and summary_low[s_str_e] in e_symb:
       return True


@logger.catch
def search_My_project(issues_in_proj, model, dev_type, precsn, ver, precsn_all):
   """ первоочередное найти по модели и устройству, потом искать по точности (если возможно по нескольким)."""
   logger.debug('**** search_My_project_number **************')
   precsn_all.sort()
   res_issues = []
   # res_issue = []
   for founded_issue in issues_in_proj:
       model_str = ''
       for _ in model.split('_'):
           if model_str + _ == model:
               model_str = model_str + _
           else:
               model_str = model_str + _ + '_'

           if model_str == model:
               model_str_res = model_str
           else:
               model_str_res = model_str + '*'
           summary = founded_issue.fields.summary
           if search_in_summary(summary, model_str_res) and\
                   search_in_summary(summary, dev_type):
               # Нашли модель и тип устройства (CPU, GPU, GNA итд) в summary...
               res_issues.append(founded_issue)
   logger.debug(f'res_issues: {res_issues}')
   if len(res_issues) > 1:
       # Ищем по точности - все подходящие варианты.
       found_from_precsn_all = []
       # found_precsn = 0
       for _ in res_issues:
           found_precsn = 0
           for i in precsn_all:
               if search_in_summary(_.fields.summary, i):
                   found_precsn += 1
                   # found_from_precsn_all.append((_, found_precsn))
                   found_from_precsn_all.append(_)
                   break
       logger.debug(f'found_from_precsn_all: {found_from_precsn_all}')
       res_issue = found_from_precsn_all
       # precsn_number = 0
       # for _ in found_from_precsn_all:
       #     if precsn_number < _[1]:
       #         precsn_number = _[1]
       #         res_issue = _[0]
   # elif len(res_issues) == 1:
   #     res_issue = res_issues[0]
   # elif len(res_issues) == 0:
   #     res_issue = ''
   else:
       res_issue = res_issues
   logger.debug(f'search_My_project_number res_issue: {res_issue}')
   logger.debug('**** END search_My_project_number **************')
   return res_issue


@logger.catch
def search_descr_comm(issue, ver):
   is_descr = False
   is_comment = False

   is_ztest = False
   for _ in issue.fields.components:
       if _ == 'z-Automation Test':
           is_ztest = True

   descr = issue.fields.description

   if descr and descr.find(ver) != -1 and descr.find(REP_ON) != -1:
       is_descr = True
       logger.debug(f'res_issue_descr: {issue.key}, issue.description: {descr}')

   if not is_descr:
       issue_f = jira.issue(issue.key)
       comments = issue_f.fields.comment.comments
       for _ in comments:
           comm_body = jira.comment(issue.key, _).body
           if comm_body.find(ver) != -1 and comm_body.find(REP_ON) != -1:
               is_comment = True
               logger.debug(f'res_issue_comments: {issue.key}, issue.summary: {issue.fields.summary}')

   if is_descr or is_comment:
       logger.debug('__________________________________________________________')
   return is_descr, is_comment, is_ztest


if __name__ == "__main__":
   # Замеряем время начала выполнения программы
   t_start = time.monotonic()
   logger.info("")
   logger.info("******************************************************")
   logger.info('Wait...')

   start_time = time.time()
   logger.info(time.ctime(start_time))
   logger.info("")

   args = get_args(create_parser())
   logger.info(args)
   arg1 = args.report_file
   logger.info(f'arg1 = {arg1}')

   index1 = arg1.find('.')
   index2 = arg1.find('.txt')
   version = arg1[index1 - 4:index2]
   logger.warning(f'version = {version}')

   report_type = ''
   if 'acc' in arg1:
       report_type = 'acc'
       bug_labels = 'accweek'
   elif 'perf' in arg1:
       report_type = 'perf'
       bug_labels = 'perfweek'

   logger.info(f'report_type = {report_type}')

   jira = JIRA(options={'server': SERVER, 'verify': False}, token_auth=APIKEY)

   text = ''
   count = 0
   index1 = index2 = 0
   list_of_string_number = []
   link_srch = False
   line_eof = 0
   try:
       with open(arg1) as f:
           lines = f.readlines()
           eof = f.tell()  # Находим конец файла
           logger.debug(f'**** eof = {eof}')

           for n, line in enumerate(lines):
               count += line.count("Reproduced on")  # Число строк с шаблоном "Reproduced on"
               # Список с номерами строк, где встречается шаблон, как начало с данными и заносим их в список
               if line.find("Reproduced on") != -1:
                   list_of_string_number.append(n)
               # Проверяем, достигли ли конца файла при построчном чтении и определяем номер строки с концом файла
               if eof:
                   line_eof = n

           list_of_string_number.append(line_eof)  # Добавление строки с концом файла в список
           logger.debug(f'**** line_eof = {line_eof}')
           logger.debug(f'**** list_of_string_number = {list_of_string_number}')
           logger.debug(f'**** count = {count}')

           # В цикле проходим по списку list_of_string_number с номерами строк
           # Текст между парами индексов из списка сформирован для внесения в баг
           # Если нужно создать новый баг, то из этого текста формируем шапку бага
           i = 0
           new_issue_list = []

           with open('new_bug.txt', 'w') as nb:
               nb.write(str(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")) + '\r\n')
           with open('new_comment.txt', 'w') as nbo:
               nbo.write(str(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")) + '\r\n')

           while i < count:
               logger.debug('\n')
               logger.debug(' *****************************************************************************')
               logger.debug(f' **************** Start of loop: i = {i+1} from count = {count} **********************')
               logger.debug(' *****************************************************************************\n')

               f.seek(0)
               index1 = list_of_string_number[i]
               if index1 == line_eof:
                   logger.debug(f'**** index1 = line_eof = {line_eof}\t*** This is end of file ***\n')
                   break
               index2 = list_of_string_number[i + 1]
               logger.debug(f'**** index1 = {index1}')
               logger.debug(f'**** index2 = {index2}')
               lines = f.readlines()[index1:index2 - 1]
               # logger.debug(f'**** lines = \n{lines}\n')
               text_to_bug = ''.join(lines)
               logger.debug(f'**** text_to_bug = \n{text_to_bug}')

               temp_file_create(temp_file, text_to_bug)
               model, fw, platform, dev, precsn, ver, short_link, precsn_all = file_read_params(temp_file, 'r', report_type, index2 - index1 - 3)
               precsn_all = list(set(precsn_all))
               precsn_all.sort()
               logger.debug(f'**** found_model = {model}')
               logger.debug(f'**** found_fw = {fw}')
               logger.debug(f'**** found_platform = {platform}')
               logger.debug(f'**** fount_dev = {dev}')
               logger.debug(f'**** found_precsn = {precsn}')
               logger.debug(f'**** precsn_all = {precsn_all}')
               logger.debug(f'**** ver = {ver}')
               logger.debug(f'**** link = {short_link}')

               jql = (f'project = My_project AND issuetype = Bug AND status in (Open, Assigned, Deferred, Implemented,'
                      f' "In Progress", "In Review", Pending, Verified) AND '
                      f'labels = {bug_labels} AND text ~ "{model}" '
                      f'ORDER BY issuetype DESC, created DESC')
               search_issues_in_proj = jira.search_issues(jql)
               # Список багов на обновление... если нет, то новый. - создавать еденичные если есть массовый???
               My_project = []
               My_project = search_My_project(search_issues_in_proj, model, dev, precsn, ver, precsn_all)
               logger.debug(f'My_project: {My_project, len(My_project)}')
               if len(My_project) > 0:
                   for _ in My_project:
                       logger.debug(f'My_project: {_.key, _.fields.summary}')
                       is_descr, is_comment, is_ztest = search_descr_comm(_, ver)
                       if not is_descr and not is_comment:
                           #   добавляем коммент.
                           new_comment = jira.add_comment(_, text_to_bug)

                           if is_ztest:
                               _.update(fields={"components": 'Validation'})

                           logger.debug(f'new_comment: {new_comment}')
                           with open('new_comment.txt', 'a') as nbo:
                               nbo.write(f'add_comment: {new_comment}\r\n')

               else:
                   # Создаем новую багу.
                   cs = create_summary(model, fw, platform, dev, str(precsn_all), report_type)
                   logger.debug(f'create_summary: {cs}')

                   if COMP_BY_DEFAULT in ['Validation', 'Test']:
                       assign = ASSIGNEE_USER
					
					#вырезано подставление имен в зависимости от проекта.

                   logger.debug(f"assign = {assign}")

                   new_issue = jira.create_issue(project='My_project',
                                                 issuetype={'name': 'Bug'},
                                                 assignee={'name': assign},
                                                 summary=cs,
                                                 description=text_to_bug,
                                                 components=[{'name': COMP_BY_DEFAULT}],
                                                 versions=[{'name': BUG_VERSION}],
                                                 customfield_13805={'value': '3-Medium'},
                                                 labels=[bug_labels]
                                                 )
                   new_issue_list.append(new_issue)
                   with open('new_bug.txt', 'a') as nb:
                       nb.write(str(new_issue) + '\r\n')

               i += 1
           logger.debug(f'new_issue_list: {str(new_issue_list)}')
           # new_issues = jira.create_issues(field_list=new_issue_list)
           # logger.debug(f'new_issues: {str(new_issues)}')
           # with open('new_bug.txt', 'w') as nb:
           #     nb.write(str(new_issue_list))

   except FileNotFoundError:
       logger.debug(f"File {arg1} not found!")
   finally:
       f.close()

   # Замеряем время окончания выполнения программы
   logger.info("")
   t_stop = time.monotonic()
   # вычисляем разницу во времени
   t_run = t_stop - t_start
   logger.info(f'Work time = {int(t_run // 60)} min. {round((t_run % 60), 3)} sec.')
   logger.info("")


