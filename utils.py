import os
from csv import DictReader

from selenium.common import TimeoutException
from selenium.webdriver import Chrome, ChromeOptions, ActionChains
from selenium.webdriver.support import expected_conditions as exp_cond
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By

from constants import SEARCH_TIMEOUT, ERROR_PIC_FILENAME, LOAD_TIMEOUT


def get_driver(download_folder: str = '/temp/'):
    options = ChromeOptions()
    options.add_argument('--log-level=3')
    options.add_experimental_option('prefs', {'download.default_directory': download_folder})
    # options.add_argument('--headless')
    return Chrome(options=options)


def get_domain(url: str):
    return url.split('/')[2 if 'http://' in url or 'https' in url else 0]


def format_url(url: str) -> str:
    return url.split('//')[-1].rstrip('/').replace('/', '-')


def handle_exception(driver: Chrome, exception_cls, text: str, error_pic_filename: str):
    driver.save_screenshot(error_pic_filename)
    return exception_cls(f'{text} (см. {error_pic_filename})')


def assert_count_rows(filename, count):
    with open(filename, encoding='utf-8') as f:
        length = len(f.readlines()) - 1
        scale = int(count) * 0.99 if int(count) * 0.99 >= 1 else count - 1
        return True if scale <= length <= count else False


def load_data_from_file(filename: list[str], extra_fields: dict = None, delimiter: str = ','):
    with open(filename, encoding='utf-8') as f:
        reader = DictReader(f, f.readline().strip().split(delimiter), delimiter=delimiter)
        return (list(reader) if not extra_fields or not isinstance(extra_fields, dict)
                else [{**extra_fields, **row} for row in reader])


def parse_url(driver: Chrome, search_url: str, base_url: str, url_suffix: str,
              search_type: str):
    driver.get(base_url.rstrip('/') + '/' + (url_suffix.lstrip('/') % (search_type, search_url)))
    if get_export_rows_count(driver) == 0:
        return [], []
    i = -1
    temp_data = []
    while True:
        i += 1
        countries_btn = WebDriverWait(driver, SEARCH_TIMEOUT).until(exp_cond.presence_of_element_located(
            (By.XPATH, '//div[@class="css-1m3jbw6-dropdown css-mkifqh-dropdownMenuWidth '
                       'css-1sspey-dropdownWithControl"]/button')))
        countries_btn.click()
        try:
            country_block = WebDriverWait(driver, SEARCH_TIMEOUT).until(exp_cond.presence_of_all_elements_located(
                (By.XPATH, '//div[@class="css-kt22mo-dropdownBaseMenu css-6vm5e4-countrySelectInnerMenu"]'
                           '//div[@class="css-1idz3us-countrySelectItem"]')))[i]
        except TimeoutException as e:
            raise handle_exception(driver, e.__class__, 'Не удалось найти список стран', ERROR_PIC_FILENAME)
        country = country_block.find_element(
            By.XPATH, './/div[@class="css-a5m6co-text css-p8ym46-fontFamily '
                      'css-11397xj-fontSize css-15qzf5r-display"]').text.strip()
        keywords_count = country_block.find_element(
            By.XPATH, './/div[@class="css-a5m6co-text css-10st79w-fontFamily '
                      'css-1s1cif8-fontSize css-15qzf5r-display"]').text.strip()
        if keywords_count == '0':
            break
        country_block.click()
        if i > 0:
            try:
                results_btn = WebDriverWait(driver, SEARCH_TIMEOUT).until(exp_cond.presence_of_element_located(
                    (By.XPATH, '//button[@class="css-15qe8gh-button css-1i73y9f-buttonFocus css-1emi1z8-buttonWidth '
                               'css-15kjecu-buttonHeight css-q66qvq-buttonCursor"]')))
            except TimeoutException as e:
                raise handle_exception(driver, e.__class__, 'Не удалось найти кнопку результатов',
                                       ERROR_PIC_FILENAME)
            try:
                results_btn.click()
            except Exception as e:
                raise handle_exception(driver, e.__class__, 'Не удалось нажать на кнопку результатов',
                                       ERROR_PIC_FILENAME)
        temp_data.append((export(driver, search_url, country), country))
    output, countries = [], []
    for filename, country in temp_data:
        countries.append(country)
        output += load_data_from_file(filename, extra_fields={'Country': country})
    return output, countries


def get_export_rows_count(driver: Chrome):
    try:
        return int(WebDriverWait(driver, LOAD_TIMEOUT).until(exp_cond.presence_of_element_located(
            (By.XPATH, '//*[@class="css-a5m6co-text css-p8ym46-fontFamily css-11397xj-fontSize '
                       'css-1wmho6b-fontWeight css-mun6jo-color css-15qzf5r-display"]'))
        ).text.split()[0].replace(',', ''))
    except (TimeoutException, ValueError) as e:
        raise handle_exception(driver, e.__class__, 'Не удалось получить количество строк',
                               ERROR_PIC_FILENAME)


def export(driver: Chrome, search_url: str, country: str):
    rows_count = get_export_rows_count(driver)
    try:
        export_btn = WebDriverWait(driver, SEARCH_TIMEOUT).until(exp_cond.presence_of_element_located(
            (By.XPATH, '//button[@class="css-15qe8gh-button css-ykx4dy-buttonFocus '
                       'css-1emi1z8-buttonWidth css-15kjecu-buttonHeight css-q66qvq-buttonCursor"]')))
    except TimeoutException as e:
        raise handle_exception(driver, e.__class__, 'Не удалось найти кнопку экспорта', ERROR_PIC_FILENAME)
    try:
        export_btn.click()
    except Exception as e:
        raise handle_exception(driver, e.__class__, 'Не удалось нажать на кнопку экспорта',
                               ERROR_PIC_FILENAME)
    # ActionChains(driver).move_by_offset(10, 20).perform()
    try:
        input_fields = WebDriverWait(driver, LOAD_TIMEOUT).until(
            exp_cond.presence_of_all_elements_located((By.XPATH, '//input[@name="export-encoding-options"]/..')))
    except TimeoutException:
        raise handle_exception(driver, TimeoutException,
                               'Не удалось установить кодировку при экспорте', ERROR_PIC_FILENAME)
    input_fields[-1].click()
    try:
        row_fields = WebDriverWait(driver, LOAD_TIMEOUT).until(
            exp_cond.presence_of_all_elements_located((By.XPATH, '//input[@name="export-number-of-rows"]/..')))
    except TimeoutException:
        raise handle_exception(driver, TimeoutException,
                               'Не удалось установить количество строчек при экспорте', ERROR_PIC_FILENAME)
    if len(row_fields) == 3:
        if '(' in row_fields[1].text and ')' in row_fields[1].text:
            try:
                row_limit = int(row_fields[1].text.split()[1].strip().replace(",", ""))
            except Exception as e:
                raise handle_exception(driver, e.__class__, 'Не удалось распарсить лимит', ERROR_PIC_FILENAME)
            print(f'[{search_url}] Выгрузка по {country} ограничена лимитом аккаунта в '
                  f'{row_limit} строк')
            rows_count = row_limit
        row_fields[1].click()
    try:
        download_btn = WebDriverWait(driver, LOAD_TIMEOUT).until(
            exp_cond.presence_of_element_located(
                (By.XPATH, '//button[@class="css-15qe8gh-button css-1i73y9f-buttonFocus '
                           'css-1emi1z8-buttonWidth css-15kjecu-buttonHeight css-q66qvq-buttonCursor"]')))
    except TimeoutException:
        raise handle_exception(driver, TimeoutException,
                               'Не удалось произвести экспорт', ERROR_PIC_FILENAME)
    download_btn.click()
    if not os.path.exists('temp'):
        os.mkdir('temp')
    old_temp_files = set(os.listdir('temp'))
    while True:
        try:
            new_temp_files = set(os.listdir('temp'))
            if len(new_temp_files) != len(old_temp_files):
                difference = new_temp_files.difference(old_temp_files).pop()
                if (not difference.endswith('.tmp') and not difference.endswith('.crdownload')
                    and os.path.getsize(os.path.join('temp', difference))) \
                        and (assert_count_rows(os.path.join('temp', difference), rows_count)):
                    return os.path.join('temp', difference)
        except PermissionError:
            continue