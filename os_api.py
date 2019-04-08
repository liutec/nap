import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import optparse

from keystoneauth1.identity import Password as KeystonePassword
from keystoneauth1.session import Session as KeystoneSession
from glanceclient.client import Client as GlanceClient
from novaclient.client import Client as NovaClient


def make_keystone_session(url, username, password, project_name=None):
    auth = KeystonePassword(
        auth_url=url,
        username=username,
        password=password,
        project_name=project_name,
        project_domain_id='default',
        project_domain_name='default',
        user_domain_id='default',
        user_domain_name='default'
    )

    # build session and client
    return KeystoneSession(auth=auth, verify=False)


def make_glance_client(session):
    return GlanceClient('2', session=session)


def make_nova_client(session):
    return NovaClient('2', session=session)


def fetch_all_images(session):
    glance_client = make_glance_client(session)
    images_generator = glance_client.images.list()
    return [image for image in images_generator]


def get_image_by_name(images, image_name):
    for image in images:
        if image.name == image_name:
            return image
    return None


def print_images(title, images):
    print("\n%s:" % title)
    for image in images:
        print("- %s" % '\t'.join([image.id, image.updated_at, image.name]))


def print_flavors(title, flavors):
    print("\n%s:" % title)
    for flavor in flavors:
        print("- %s" % '\t'.join([flavor.id, flavor.updated_at, flavor.name]))


def get_all_flavors(session):
    nova_client = make_nova_client(session)
    return [flavor for flavor in nova_client.flavors.list()]


def get_flavor_by_name(flavors, flavor_name):
    for flavor in flavors:
        if flavor.name == flavor_name:
            return flavor
    return None


def create_vm(session, server_name, image_id, flavor_id, meta=None, timeout=None):
    nova_client = make_nova_client(session)

    server = nova_client.servers.create(
        name=server_name,
        image=image_id,
        flavor=flavor_id,
        meta=meta,
        key_name='default',
        security_groups=['default']
    )

    print('Waiting for server %s to become active' % server.id)
    start_time = time.time()
    while True:
        if server.status == 'ACTIVE':
            break
        if server.status == 'ERROR':
            if hasattr(server, 'fault') and isinstance(server.fault, dict):
                raise Exception(server.fault.get('message'))
            raise Exception('Unable to create server. Error cause not reported by OpenStack.')
        if timeout:
            duration = time.time() - start_time
            if duration > timeout:
                raise Exception('Timeout waiting for server to become active (%.2f sec)' % duration)
        time.sleep(1)
        server = nova_client.servers.get(server.id)

    return server


def delete_vm(session, server_id):
    nova_client = make_nova_client(session)
    server = nova_client.servers.get(server_id)
    server.delete()


def parse_args():
    parser = optparse.OptionParser()
    parser.add_option('-u', '--keystone-url', dest='keystone_url', type='str',
                      help='OpenStack Keystone URL.', default=None)
    parser.add_option('-n', '--keystone-username', dest='keystone_username', type='str',
                      help='OpenStack username.', default=None)
    parser.add_option('-w', '--keystone-password', dest='keystone_password', type='str',
                      help='OpenStack password.', default=None)
    parser.add_option('-p', '--project', dest='project', type='str',
                      help='OpenStack project name.', default=None)
    parser.add_option('-i', '--image-name', dest='image_name', type='str',
                      help='OpenStack image name.', default=None)
    parser.add_option('-f', '--flavor-name', dest='flavor_name', type='str',
                      help='OpenStack flavor name.', default=None)
    parser.add_option('-m', '--server-name', dest='server_name', type='str',
                      help='OpenStack server name.', default=None)
    parser.add_option('-s', '--server-id', dest='server_id', type='str',
                      help='OpenStack server Id.', default=None)
    (options, args) = parser.parse_args()

    if options.keystone_url is None:
        parser.error('OpenStack Keystone URL not given.')
    if options.keystone_username is None:
        parser.error('OpenStack username not given.')
    if options.keystone_password is None:
        parser.error('OpenStack password not given.')
    if options.project is None:
        parser.error('OpenStack project not given.')

    return parser, options, args


def main():
    (parser, options, args) = parse_args()

    if len(args) < 1:
        raise Exception("Please specify action")

    session = make_keystone_session(
        url=options.keystone_url,
        username=options.keystone_username,
        password=options.keystone_password,
        project_name=options.project
    )

    if args[0] == 'list-images':
        images = fetch_all_images(session)
        print_images('Images', images)
        return 0

    if args[0] == 'list-flavors':
        flavors = get_all_flavors(session)
        print_flavors('Flavors', flavors)
        flavor = get_flavor_by_name(flavors, options.flavor_name)
        if not flavor:
            raise Exception('Flavor "%s" not found.' % options.flavor_name)
        return 0

    if args[0] == 'create-vm':
        if options.image_name is None:
            parser.error('OpenStack image name not given.')
        if options.server_name is None:
            parser.error('OpenStack server name not given.')
        images = fetch_all_images(session)
        image = get_image_by_name(images, options.image_name)
        if not image:
            raise Exception('Image "%s" not found.' % options.image_name)
        flavors = get_all_flavors(session)
        flavor = get_flavor_by_name(flavors, options.flavor_name)
        if not flavor:
            raise Exception('Flavor "%s" not found.' % options.flavor_name)
        server = create_vm(session, options.server_name, image.id, flavor.id)
        print('Created server %s' % server.id)
        return 0

    if args[0] == 'delete-vm':
        if options.server_id is None:
            parser.error('OpenStack server id not given.')
        delete_vm(session, options.server_id)
        print('Deleted server %s' % options.server_id)
        return 0


if __name__ == '__main__':
    exit(main())
