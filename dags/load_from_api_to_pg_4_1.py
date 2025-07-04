from datetime import datetime   

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook

DEFAULT_ARGS = {   #обязательно в начале кода
    'owner': 'admin',
    'retries': 2,
    'retry_delay': 600,
    'start_date': datetime(2024, 11, 12),
}

API_URL = "https://b2b.itresume.ru/api/statistics"


def load_from_api(**context):
    import requests   #импорты внутри функции!!!!
    import pendulum
    import psycopg2 as pg
    import ast

    payload = {
        'client': 'Skillfactory',
        'client_key': 'M2MGWS',
        'start': context['ds'], #формат '2025-07-03'
        'end': pendulum.parse(context['ds']).add(days=1).to_date_string(),
    }
    response = requests.get(API_URL, params=payload)
    data = response.json()

    connection = BaseHook.get_connection('conn_pg')  #получаем данные для подключения (креды)

    with pg.connect(
        dbname='etl',
        sslmode='disable', #отключаем sslmode -что это?
        user=connection.login,
        password=connection.password,
        host=connection.host,
        port=connection.port,
        connect_timeout=600,
        keepalives_idle=600,
        tcp_user_timeout=600
    ) as conn:
        cursor = conn.cursor()

        for el in data:
            row = []
            passback_params = ast.literal_eval(el.get('passback_params') if el.get('passback_params') else '{}') 
            #выше превращаем содержимое строки в словарь
            row.append(el.get('lti_user_id'))
            row.append(True if el.get('is_correct') == 1 else False)
            row.append(el.get('attempt_type'))
            row.append(el.get('created_at'))
            row.append(passback_params.get('oauth_consumer_key'))
            row.append(passback_params.get('lis_result_sourcedid'))
            row.append(passback_params.get('lis_outcome_service_url'))

            cursor.execute("INSERT INTO admin_table VALUES (%s, %s, %s, %s, %s, %s, %s)", row)

        conn.commit()


with DAG(
    dag_id="load_from_api_to_pg", #используем уникальное имя или почту
    tags=['4', 'admin'],
    schedule='@daily',
    default_args=DEFAULT_ARGS,
    max_active_runs=1, #сколько дагранов одновременно будет работать. Обязательно ставим
    max_active_tasks=1   #сколько тасок одновременно будет работать в одном дагране. Обязательно ставим
) as dag:

    dag_start = EmptyOperator(task_id='dag_start') #начало и конец - для структуры. Бест практис
    dag_end = EmptyOperator(task_id='dag_end') #если нужно перезапустить даг - очищаем 'dag_start'. Если следующие - 'dag_end'

    load_from_api = PythonOperator(
        task_id='load_from_api', #уникальное в рамках дага имя таски
        python_callable=load_from_api,
    )

    dag_start >> load_from_api >> dag_end  #пайплайн
