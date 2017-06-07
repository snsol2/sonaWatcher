import json
from datetime import datetime

from api.sbapi import SshCommand
from api.sona_log import LOG
from api.watcherdb import DB

def parse_command(req_obj):
    try:
        res_body = dict()
        res_body['command'] = req_obj['command']
        res_body['system'] = req_obj['system']

        try:
            res_body['param'] = req_obj['param']
        except:
            res_body['param'] = ''

        ret = COMMAND_MAP[req_obj['command']](req_obj['system'], req_obj['param'])
        res_body['result'] = ret
        res_body['time'] = str(datetime.now())

        return res_body
    except:
        LOG.exception()
        return {'Result': 'FAIL'}

def regi_url(url, auth):
    try:
        sql = 'SELECT * FROM ' + DB.REGI_SYS_TBL + ' WHERE url = \'' + url + '\''
        sql_evt = 'SELECT * FROM ' + DB.EVENT_TBL

        with DB.connection() as conn:
            url_info = conn.cursor().execute(sql).fetchall()
            evt_list = conn.cursor().execute(sql_evt).fetchall()
        conn.close()

        event_list = []

        for nodename, item, grade, desc, time in evt_list:
            if not grade in ['ok', 'normal']:
                evt = {'event': 'occur', 'system': nodename, 'item': item, 'grade': grade, 'desc': desc, 'time': time}
                event_list.append(evt)

        # if already exist
        if len(url_info) == 1:
            res_body = {'Result': 'SUCCESS', 'Event list': event_list}
        else:
            # insert db
            sql = 'INSERT INTO ' + DB.REGI_SYS_TBL + ' VALUES (\'' + url  + '\', \'' + auth + '\' )'

            ret = DB.sql_execute(sql)

            if ret == 'SUCCESS':
                res_body = {'Result': 'SUCCESS', 'Event list': event_list}
            else:
                res_body = {'Result': 'FAIL'}

        return res_body
    except:
        LOG.exception()
        return {'Result': 'FAIL'}

def unregi_url(url):
    try:
        sql = 'SELECT * FROM ' + DB.REGI_SYS_TBL + ' WHERE url = \'' + url + '\''

        with DB.connection() as conn:
            url_info = conn.cursor().execute(sql).fetchall()

        conn.close()

        # if no exist
        if len(url_info) == 0:
            res_body = {'Result': 'SUCCESS'}
        else:
            # delete db
            sql = 'DELETE FROM ' + DB.REGI_SYS_TBL + ' WHERE url = \'' + url + '\''

            ret = DB.sql_execute(sql)

            if ret == 'SUCCESS':
                res_body = {'Result': 'SUCCESS'}
            else:
                res_body = {'Result': 'FAIL'}

        return res_body
    except:
        LOG.exception()
        return {'Result': 'FAIL'}


def proc_dis_system(node, dummy):
    try:
        sql = 'SELECT ' + DB.STATUS_TBL + '.nodename, ' + DB.NODE_INFO_TBL + '.ip_addr, ' + DB.item_list + ' FROM ' + DB.STATUS_TBL + \
              ' INNER JOIN ' + DB.NODE_INFO_TBL + ' ON ' + DB.STATUS_TBL + '.nodename = ' + DB.NODE_INFO_TBL + '.nodename'

        if not node == 'all':
            sql = sql + ' WHERE nodename = \'' + node + '\''

        with DB.connection() as conn:
            nodes_info = conn.cursor().execute(sql).fetchall()
        conn.close()

        result = dict()

        for nodename, ip, ping, app, web, cpu, memory, disk, ovsdb, of, cluster, node, vrouter, ha_stats, ha_ratio, gw_ratio in nodes_info:
            node_type = get_node_list(nodename, 'type')
            type = str(node_type[0][0]).upper()

            if 'ONOS' == type:
                result[nodename] = {'TYPE': type, 'IP': ip, 'NETWORK': ping, 'ONOS_APP': app, 'ONOS_REST': web, 'CPU': cpu, 'MEMORY': memory, 'DISK': disk,
                                    'ONOS_OVSDB': ovsdb, 'ONOS_OF': of, 'ONOS_CLUSTER': cluster, 'ONOS_HA_LIST': ha_stats, 'ONOS_HA_RATIO': ha_ratio, 'OPENSTACK_NODE': node}
            elif 'SWARM' == type:
                result[nodename] = {'TYPE': type, 'IP': ip, 'NETWORK': ping, 'SWARM_SVC': app, 'CPU': cpu, 'MEMORY': memory, 'DISK': disk, 'SWARM_NODE': node}
            elif 'OPENSTACK' == type:
                result[nodename] = {'TYPE': type, 'IP': ip, 'NETWORK': ping, 'CPU': cpu, 'MEMORY': memory, 'DISK': disk, 'VROUTER': vrouter, 'TRAFFIC_GW': gw_ratio}
            elif 'XOS' == type:
                result[nodename] = {'TYPE': type, 'IP': ip, 'NETWORK': ping, 'CPU': cpu, 'MEMORY': memory, 'DISK': disk}

        return result
    except:
        LOG.exception()
        return {'Result': 'FAIL'}

def proc_dis_resource(node, param):
    nodes_info = get_node_list(node, 'nodename, ' + param, DB.RESOURCE_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    res_result = dict()
    for nodename, value in nodes_info:
        if value < 0:
            res_result[nodename] = 'FAIL'
        else:
            res_result[nodename] = value

    return res_result


def proc_dis_onos(node, param):
    if param == 'app':
        nodes_info = get_node_list(node, 'nodename, applist', DB.ONOS_TBL)

    if param == 'web':
        nodes_info = get_node_list(node, 'nodename, weblist', DB.ONOS_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    res_result = dict()
    for nodename, list in nodes_info:
        if list == 'fail' or list == 'none':
            res_result[nodename] = 'FAIL'
        else:
            res_result[nodename] = list

    return res_result


def proc_dis_log(node, param):
    cmd = 'ld'

    if param == 'debug':
        cmd = 'ld -l DEBUG'
    elif param == 'info':
        cmd = 'ld -l INFO'
    elif param == 'error':
        cmd = 'ld -l ERROR'
    elif param == 'exception':
        cmd = 'log:exception-display'

    nodes_info = get_node_list(node, 'nodename, ip_addr, type')

    res_result = dict()
    for node_name, ip, type in nodes_info:
        if type.upper() == 'ONOS':
            log_crt = SshCommand.onos_ssh_exec(ip, cmd)

            if log_crt is not None:
                res_result[node_name] = log_crt
            else:
                res_result[node_name] = 'FAIL'

    return res_result


def proc_dis_vrouter(node, param):
    nodes_info = get_node_list(node, 'nodename, ' + param, DB.OPENSTACK_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    res_result = dict()
    for nodename, list in nodes_info:
        if list == 'fail' or list == 'none':
            res_result[nodename] = 'FAIL'
        else:
            res_result[nodename] = list

    return res_result


def proc_dis_gwratio(node, dummy):
    nodes_info = get_node_list(node, 'nodename, gw_ratio', DB.OPENSTACK_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    res_result = dict()
    for nodename, ratio in nodes_info:
        if list == 'fail' or ratio == 'none':
            res_result[nodename] = 'FAIL'
        else:
            res_result[nodename] = ratio

    return res_result


def proc_dis_swarm(node, param):
    nodes_info = get_node_list(node, 'nodename, ' + param, DB.SWARM_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    res_result = dict()
    for nodename, list in nodes_info:
        if list == 'fail' or list == 'none':
            res_result[nodename] = 'FAIL'
        else:
            res_result[nodename] = list

    return res_result


def proc_dis_xos(system, param):
    pass


def proc_dis_onosha(node, param):
    # check onos
    nodes_info = get_node_list(node, 'nodename, haproxy', DB.ONOS_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    if param == 'list':
        res_result = dict()
        for nodename, haproxy in nodes_info:
            if haproxy == 'none':
                res_result[nodename] = 'FAIL'
            else:
                res_result[nodename] = haproxy

        return res_result

    elif param == 'stats':
        sql = 'SELECT stats FROM ' + DB.HA_TBL + ' WHERE ha_key = \'HA\''

        with DB.connection() as conn:
            nodes_info = conn.cursor().execute(sql).fetchone()
        conn.close()

        for value in nodes_info:
            return json.loads(str(value).replace('\'', '\"'))

        return {'HA': 'FAIL'}

def proc_dis_node(node, param):
    if param == 'list':
        nodes_info = get_node_list(node, 'nodename, nodelist', DB.ONOS_TBL)
    elif param == 'port':
        nodes_info = get_node_list(node, 'nodename, port', DB.ONOS_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    res_result = dict()
    for nodename, value in nodes_info:
        if value == 'none':
            res_result[nodename] = 'FAIL'
        else:
            res_result[nodename] = value

    return res_result


def proc_dis_connection(node, param):
    nodes_info = get_node_list(node, 'nodename, ' + param, DB.ONOS_TBL)

    if len(nodes_info) == 0:
        return {'fail': 'This is not a command on the target system.'}

    res_result = dict()
    for nodename, value in nodes_info:
        if value == 'none':
            res_result[nodename] = 'FAIL'
        else:
            res_result[nodename] = value

    return res_result


def proc_dis_all(system, param):
    pass


def exist_command(req):
    cmd = req['command']

    if cmd not in COMMAND_MAP.keys():
        return False
    return True


def get_node_list(nodes, param, tbl = DB.NODE_INFO_TBL):
    try:
        if nodes == 'all':
            sql = 'SELECT ' + param + ' FROM ' + tbl
        else:
            sql = 'SELECT ' + param + ' FROM ' + tbl + ' WHERE nodename = \'' + nodes + '\''

        with DB.connection() as conn:
            nodes_info = conn.cursor().execute(sql).fetchall()

        conn.close()
        return nodes_info
    except:
        LOG.exception()
        return None

COMMAND_MAP = {'resource': proc_dis_resource,
               'onos-svc': proc_dis_onos,
               'onos-log': proc_dis_log,
               'vrouter-svc': proc_dis_vrouter,
               'swarm-svc': proc_dis_swarm,
               'xos-svc': proc_dis_xos,
               'onos-ha': proc_dis_onosha,
               'openstack-node': proc_dis_node,
               'onos-conn': proc_dis_connection,
               'event-list': proc_dis_all,
               'traffic-gw': proc_dis_gwratio,
               #internal command
               'system-status':proc_dis_system
               }
