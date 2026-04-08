import time
import requests
import logging
import re
import pandas as pd
from tqdm import tqdm
from random import randint
from bs4 import BeautifulSoup
from collections import defaultdict, Counter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Session-level timer: track first and last successful FetchUrl call times.
# Used to compute an adaptive wait when a connection error exhausts all retries.
_first_success_time = None
_last_success_time = None


def set_logger():
    log_file = '../spider.log'
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S',
        filename=log_file,
        filemode='a'
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)


def FetchUrl(url, max_retries=5, backoff_factor=2, timeout=30):
    '''
    功能：访问 url 的网页，获取网页内容并返回
    参数：目标网页的 url
    返回：目标网页的 html 内容
    '''
    global _first_success_time, _last_success_time

    # Normalize legacy dblp.uni-trier.de URLs to the current dblp.org domain
    url = url.replace('http://dblp.uni-trier.de/', 'https://dblp.org/')
    url = url.replace('https://dblp.uni-trier.de/', 'https://dblp.org/')

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    ]
    random_agent = USER_AGENTS[randint(0, len(USER_AGENTS) - 1)]
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'accept-encoding': 'gzip, deflate, br',
        'connection': 'keep-alive',
        'upgrade-insecure-requests': '1',
        'cache-control': 'max-age=0',
        'user-agent': random_agent,
    }

    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    last_exc = None
    for attempt in range(1, max_retries + 1):
        wait = backoff_factor ** attempt
        try:
            r = session.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding
            now = time.time()
            if _first_success_time is None:
                _first_success_time = now
            _last_success_time = now
            time.sleep(randint(2, 5))  # polite delay after each successful request
            return r.text
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            logging.info('连接失败（第{}次），{}秒后重试: {}'.format(attempt, wait, e))
            time.sleep(wait)
        except requests.exceptions.Timeout as e:
            last_exc = e
            logging.info('请求超时（第{}次），{}秒后重试: {}'.format(attempt, wait, e))
            time.sleep(wait)

    # All retries exhausted — adaptive wait: sleep for the full session duration so
    # the rate-limit window has time to reset before the caller handles the error.
    if _first_success_time is not None and _last_success_time is not None:
        session_duration = max(_last_success_time - _first_success_time, 30)
        logging.info('自适应等待 {:.0f}秒（本次会话已运行时长）'.format(session_duration))
        time.sleep(session_duration)

    if last_exc is not None:
        raise last_exc
    raise requests.exceptions.ConnectionError('FetchUrl failed after {} retries: {}'.format(max_retries, url))


def ccf_filter(no: int, rank='A/B/C'):
    '''
    对某一类别所含期刊和会议名称的检索，以名称列表形式返回
        1-计算机体系结构/并行与分布计算/存储系统；6-计算机科学理论
        2-计算机网络；7-计算机图形学与多媒体
        3-网络与信息安全；8-人工智能
        4-软件工程/系统软件/程序设计语言；9-人机交互与普适计算
        5-数据库/数据挖掘/内容检索；10-交叉/综合/新兴
    :param no: 整数型，期刊/会议类别，取值范围1 ~10
    :param rank: 字符串型，可选期刊/会议等级“A/B/C”，默认全选
    :return: 该类别下的期刊/会议名称列表name_list
    '''
    ccf_catalog = '../paper_db/ccf_catalog.csv'
    df = pd.read_csv(ccf_catalog)
    duplicate_abbr = ccf_duplicate_abbr()

    venue_list = []
    for r in rank.split('/'):
        filter_df = df.query('category=={} & rank=="{}"'.format(no, r))
        abbrs = filter_df['abbr'].to_list()
        names = filter_df['name'].to_list()
        for i, abbr in enumerate(abbrs):
            if pd.isna(abbr) or abbr == '' or abbr in duplicate_abbr:
                venue_list.append(names[i])
            else:
                venue_list.append(abbr)

    return venue_list


def ccf_duplicate_abbr():
    # 返回CCF推荐表中abbr重复的会议/期刊的全称
    ccf_catalog = '../paper_db/ccf_catalog.csv'
    df = pd.read_csv(ccf_catalog)

    abbrs = df['abbr'].to_list()  # 重复最多的是空串或nan，即没有简称，循环时略过

    duplicate_abbr = list()
    for abbr, count in dict(Counter(abbrs)).items():
        if pd.isna(abbr) or abbr == '':
            continue
        if count == 2:
            duplicate_abbr.append(abbr)

    return duplicate_abbr


def ccf_not_dblp():
    '''
    统计ccf_catalog.csv中url非dblp的数会议/期刊，将其abbr/name存储到stat.py中的列表no_dblp
    使用时直接 'from stat_info import no_dblp'
    '''
    ccf_catalog = '../paper_db/ccf_catalog.csv'
    df = pd.read_csv(ccf_catalog)

    no_dblp = list()
    for i in range(len(df)):
        row_se = df.iloc[i]
        if 'http://dblp' not in str(row_se['url']) and 'https://dblp' not in str(row_se['url']):  # 非dblp数据库
            if pd.isna(row_se.abbr) or row_se.abbr == '':
                no_dblp.append(row_se['name'])
            else:
                no_dblp.append(row_se['abbr'])

    return no_dblp


def dblp_jour_frame_copy(venue, url):
    # 有的会议近几年的论文发表在期刊上，见‘https://dblp.uni-trier.de/db/conf/fse/index.html’
    # 这些论文需要解析新的journal url

    html_doc = FetchUrl(url)
    soup = BeautifulSoup(html_doc, 'html.parser')

    paper_db = list()
    main_content = soup.find('div', attrs={'id': 'main'})
    for chil in main_content.children:  # 在主页面定位包含含论文页url的block
        if chil.name == 'ul':
            try:
                tmp = chil.li.a
                volumes_info = chil
                break
            except:
                continue

    for volume in volumes_info.find_all('li'):
        db_year = dict()
        db_year['name'] = venue

        pattern = re.compile('(19|20)[0126789][0-9]')
        conf_year = re.search(pattern, volume.text).group()

        db_year['year'] = conf_year  # 出版年份
        db_year['info'] = volume.text.strip()  # 该年度出版的卷编号
        db_year['count'] = 0
        db_year['papers'] = list()

        # 获取年度期刊的子卷，同时获取跳转下一页面（论文页面）的url
        vol_url_tags = volume.find_all('a')
        paper_titles = list()
        for a_tag in vol_url_tags:
            paper_page_url = a_tag['href']

            new_html_doc = FetchUrl(paper_page_url)
            new_soup = BeautifulSoup(new_html_doc, 'html.parser')

            papers_sub_venue = new_soup.find_all('li', attrs={'class': 'entry article'})
            db_year['count'] += len(papers_sub_venue)

            logging.info('{}\t{}'.format(venue, db_year['year']))
            for paper_info in tqdm(papers_sub_venue):
                paper_title = paper_info.find('span', attrs={'class': 'title'}).text
                paper_titles.append(paper_title)

        db_year['papers'] = paper_titles
        paper_db.append(db_year)

    return paper_db


def dblp_conf_two_type(p_soup, venue):
    # 有的会议论文列表两种形式混杂，见‘https://dblp.uni-trier.de/db/conf/ches/index.html’
    # 处理完只有一种形式后，对另一种形式单独处理,判断依据'Proccedings published in' in text
    # 多数会议子会场形式只有一种形式，执行该步骤paper_db不会有任何改变；含两种形式的则会新增数据

    db_sub_venue = dict()
    sub_name = p_soup.text
    db_sub_venue['sub_name_abbr'] = ''
    db_sub_venue['sub_name'] = sub_name
    db_sub_venue['count'] = 0
    db_sub_venue['papers'] = list()

    conf_year = p_soup.previous_sibling.h2['id']
    logging.info('{}\t{}'.format(venue, conf_year))

    paper_page_url = p_soup.a['href']
    new_html_doc = FetchUrl(paper_page_url)
    new_soup = BeautifulSoup(new_html_doc, 'html.parser')

    try:
        papers_sub_venue = new_soup.find_all('li', attrs={'class': 'entry article'})
    except:
        papers_sub_venue = new_soup.find_all('li', attrs={'class': 'entry inproceedings'})
    db_sub_venue['count'] = len(papers_sub_venue)

    paper_titles = list()
    for paper_info in tqdm(papers_sub_venue):
        paper_title = paper_info.find('span', attrs={'class': 'title'}).text
        paper_titles.append(paper_title)
    db_sub_venue['papers'] = paper_titles

    return db_sub_venue, conf_year


