import os
import time
from csv import DictWriter

from dotenv import load_dotenv
from random import randint
from shutil import rmtree

from selenium.webdriver import Chrome
from selenium.common.exceptions import (NoSuchElementException, ElementClickInterceptedException,
                                        ElementNotInteractableException)
from selenium.webdriver.common.by import By

from utils import get_domain, get_driver, parse_url, format_url
from constants import *
from exceptions import *


def auth(driver: Chrome, login: str, password: str):
    login_url = os.getenv('login_url')
    if not login_url:
        raise MissingDotenvData('В переменных среды отсутствует login_url')
    driver.get(login_url)
    for input_name, verbose_name, value in [('email', 'логина', login), ('password', 'пароля', password)]:
        try:
            field = driver.find_element(By.XPATH, f'//input[@name="{input_name}"]')
        except NoSuchElementException:
            raise AuthorizationFailedException(f'Не удалось найти поле для ввода {verbose_name}')
        for s in value:
            field.send_keys(s)
            time.sleep(float(f'0.1{randint(0, 9)}'))
    try:
        driver.find_element(By.XPATH, '//button[@type="submit"]').click()
    except (NoSuchElementException, ElementClickInterceptedException, ElementNotInteractableException) as e:
        raise AuthorizationFailedException(f'Не удалось нажать на кнопку авторизации [{e.__class__.__name__}]')


def main():
    urls_filename = os.getenv('urls_filename', 'domains.txt')
    credentials_filename = os.getenv('credentials_filename', 'credentials.txt')
    temp_folder = os.getenv('temp_folder', 'temp')
    output_filename = os.getenv('output_filename', 'output.csv')
    countries_folder = os.getenv('countries_folder', 'countries')
    urls_folder = os.getenv('urls_folder', 'urls')
    delimiter = os.getenv('delimiter', ';')
    for path in output_filename, temp_folder, countries_folder, urls_folder:
        if os.path.exists(path):
            if input(f'Путь {path} будет удалён. Вы готовы продолжить? (y\\n) ').lower() != 'y':
                return
            rmtree(path) if os.path.isdir(path) else os.remove(path)
    extra_files = input('Создавать ли файлы по странам и сайтам по умолчанию? (y\\n): ').lower() == 'y'
    while True:
        try:
            search_type_idx = int(input('Укажите цифру, для какого типа соответствия собираем данные:\n'
                                        '1 – subdomains\n'
                                        '2 – prefix\n'
                                        '3 – domain\n'
                                        '4 – exact\n'))
            assert 1 <= search_type_idx <= 4
            search_type = SEARCH_TYPES[search_type_idx - 1]
            break
        except (ValueError, AssertionError):
            print('Должна быть введена цифра от 1 до 4')
    try:
        f = open(urls_filename, encoding='utf-8')
        if search_type in ('subdomains', 'domain'):
            urls = []
            for line in f:
                domain = get_domain(line.strip())
                if domain not in urls:
                    urls.append(domain)
        else:
            urls = [line.strip() for line in f.readlines()]
        f.close()
        urls_count = len(urls)
    except FileNotFoundError:
        raise InvalidFileData(f'Файла {urls_filename} не существует')
    if not urls:
        raise InvalidFileData(f'Файл {urls_filename} пуст')
    third_party_source = False
    driver = get_driver(os.path.abspath(temp_folder))
    with open(credentials_filename, encoding='utf-8') as f:
        lines = [x.strip() for x in f.readlines()]
        if len(lines) > 1:
            third_party_source = True
            login_url, base_url = lines
        else:
            base_url = os.getenv('base_url').rstrip('/')
            if not base_url:
                raise MissingDotenvData('В переменных среды отсутствует base_url')
        try:
            login, password = lines[0].split(':')
        except ValueError:
            raise InvalidFileData(f'Неверный формат данных в {os.getenv("credentials_filename")}')
    if not third_party_source:
        auth(driver, login, password)
        time.sleep(AUTH_TIMEOUT)
        if driver.current_url == os.getenv('login_url'):
            auth(driver, login, password)
    else:
        driver.get(login_url)
        print('Ожидание авторизации пользователем...')
        while driver.current_url == login_url:
            pass
    print('Авторизация прошла успешно...')
    url_suffix = os.getenv('url_suffix')
    if not url_suffix:
        raise MissingDotenvData('В переменных среды отсутствует url_suffix')
    raw_data, countries = [], []
    for i in range(urls_count):
        url_data, url_countries = parse_url(driver, urls[i], base_url, url_suffix, search_type)
        raw_data += url_data
        countries += [country for country in url_countries if country not in countries]
        print(f'[{i + 1}/{urls_count}] {urls[i]}: {len(url_data)} строк')
    headers = countries + [f'{key} {country}' for key in OUTPUT_KEYS_WO_KW for country in countries]
    urls_data = dict()
    for row in raw_data:
        cur_url = row['Current URL']
        keyword = row['Keyword']
        if cur_url not in urls_data:
            urls_data[cur_url] = dict()
        if keyword not in urls_data[cur_url]:
            urls_data[cur_url][keyword] = {header: None for header in headers}
        urls_data[cur_url][keyword][row['Country']] = row['Keyword']
        for key in OUTPUT_KEYS_WO_KW:
            val = 1 if key == 'Volume' and 0 <= int(row[key]) <= 10 else row[key]
            urls_data[cur_url][keyword][f'{key} {row["Country"]}'] = val
    # if len(raw_data) > TABLE_ROWS_LIMIT or any(len(row) > TABLE_COLS_LIMIT for row in raw_data):
    if extra_files or len(raw_data) > TABLE_ROWS_LIMIT:
        if not os.path.exists(urls_folder):
            os.mkdir(urls_folder)
        for url in urls_data:
            with open(f'{os.path.join(urls_folder, format_url(url))}.csv', 'w', newline='', encoding='utf-8') as f:
                writer = DictWriter(f, ['Current URL'] + headers, delimiter=delimiter)
                writer.writeheader()
                writer.writerows([{'Current URL': url, **urls_data[url][keyword]}
                                  for keyword in urls_data[url].keys()])
        if not os.path.exists(countries_folder):
            os.mkdir(countries_folder)
        for country in countries:
            with open(f'{os.path.join(countries_folder, country)}.csv', 'w', newline='', encoding='utf-8') as f:
                country_headers = [h for h in headers if country in h]
                writer = DictWriter(f, ['Current URL'] + country_headers, delimiter=delimiter)
                writer.writeheader()
                for url in urls_data:
                    for keyword in urls_data[url]:
                        if not urls_data[url][keyword][country]:
                            continue
                        writer.writerow({'Current URL': url, **{key: urls_data[url][keyword][key]
                                                                for key in country_headers}})
        return
    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
        writer = DictWriter(f, ['Current URL'] + headers, delimiter=delimiter)
        writer.writeheader()
        writer.writerows([{'Current URL': url, **urls_data[url][keyword]} for url in urls_data
                          for keyword in urls_data[url].keys()])


if __name__ == '__main__':
    load_dotenv()
    main()