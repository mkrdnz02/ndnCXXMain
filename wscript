# -*- Mode: python; py-indent-offset: 4; indent-tabs-mode: nil; coding: utf-8; -*-

from waflib import Context, Logs, Utils
import os, subprocess

VERSION = '0.6.3'
APPNAME = 'ndn-cxx'
PACKAGE_BUGREPORT = 'https://redmine.named-data.net/projects/ndn-cxx'
PACKAGE_URL = 'http://named-data.net/doc/ndn-cxx/'
GIT_TAG_PREFIX = 'ndn-cxx-'

def options(opt):
    opt.load(['compiler_cxx', 'gnu_dirs', 'c_osx'])
    opt.load(['default-compiler-flags', 'compiler-features',
              'coverage', 'pch', 'sanitizers', 'osx-frameworks',
              'boost', 'openssl', 'sqlite3',
              'doxygen', 'sphinx_build'],
             tooldir=['.waf-tools'])

    opt = opt.add_option_group('Library Options')

    opt.add_option('--with-examples', action='store_true', default=False,
                   help='Build examples')

    opt.add_option('--with-tests', action='store_true', default=False,
                   help='Build unit tests')

    opt.add_option('--without-tools', action='store_false', default=True, dest='with_tools',
                   help='Do not build tools')

    opt.add_option('--without-sqlite-locking', action='store_false', default=True,
                   dest='with_sqlite_locking',
                   help='Disable filesystem locking in sqlite3 database '
                        '(use unix-dot locking mechanism instead). '
                        'This option may be necessary if the home directory is hosted on NFS.')

    opt.add_option('--without-osx-keychain', action='store_false', default=True,
                   dest='with_osx_keychain', help='Do not use macOS Keychain as default TPM (macOS only)')

    opt.add_option('--enable-static', action='store_true', default=False,
                   dest='enable_static', help='Build static library (disabled by default)')
    opt.add_option('--disable-static', action='store_false', default=False,
                   dest='enable_static', help='Do not build static library (disabled by default)')

    opt.add_option('--enable-shared', action='store_true', default=True,
                   dest='enable_shared', help='Build shared library (enabled by default)')
    opt.add_option('--disable-shared', action='store_false', default=True,
                   dest='enable_shared', help='Do not build shared library (enabled by default)')

def configure(conf):
    conf.start_msg('Building static library')
    if conf.options.enable_static:
        conf.end_msg('yes')
    else:
        conf.end_msg('no', color='YELLOW')
    conf.env.enable_static = conf.options.enable_static

    conf.start_msg('Building shared library')
    if conf.options.enable_shared:
        conf.end_msg('yes')
    else:
        conf.end_msg('no', color='YELLOW')
    conf.env.enable_shared = conf.options.enable_shared

    if not conf.options.enable_shared and not conf.options.enable_static:
        conf.fatal('Either static library or shared library must be enabled')

    conf.load(['compiler_cxx', 'gnu_dirs', 'c_osx',
               'default-compiler-flags', 'compiler-features',
               'pch', 'osx-frameworks', 'boost', 'openssl', 'sqlite3',
               'doxygen', 'sphinx_build'])

    conf.env['WITH_TESTS'] = conf.options.with_tests
    conf.env['WITH_TOOLS'] = conf.options.with_tools
    conf.env['WITH_EXAMPLES'] = conf.options.with_examples

    conf.find_program('sh', var='SH', mandatory=True)

    conf.check_cxx(lib='pthread', uselib_store='PTHREAD', define_name='HAVE_PTHREAD', mandatory=False)
    conf.check_cxx(lib='rt', uselib_store='RT', define_name='HAVE_RT', mandatory=False)
    conf.check_cxx(msg='Checking for function getpass', define_name='HAVE_GETPASS', mandatory=False,
                   fragment='''#include <unistd.h>
                               int main() { getpass("Enter password"); }''')

    if conf.check_cxx(msg='Checking for netlink', define_name='HAVE_NETLINK', mandatory=False,
                      header_name=['linux/if_addr.h', 'linux/if_link.h',
                                   'linux/netlink.h', 'linux/rtnetlink.h', 'linux/genetlink.h']):
        conf.env['HAVE_NETLINK'] = True
        conf.check_cxx(msg='Checking for NETLINK_EXT_ACK', define_name='HAVE_NETLINK_EXT_ACK', mandatory=False,
                       fragment='''#include <linux/netlink.h>
                                   int main() { return NETLINK_EXT_ACK; }''')
        conf.check_cxx(msg='Checking for IFA_FLAGS', define_name='HAVE_IFA_FLAGS', mandatory=False,
                       fragment='''#include <linux/if_addr.h>
                                   int main() { return IFA_FLAGS; }''')

    conf.check_osx_frameworks()

    conf.check_sqlite3(mandatory=True)
    conf.check_openssl(mandatory=True, atleast_version=0x1000200f) # 1.0.2

    USED_BOOST_LIBS = ['system', 'filesystem', 'date_time', 'iostreams',
                       'program_options', 'chrono', 'thread', 'log', 'log_setup']

    if conf.env['WITH_TESTS']:
        USED_BOOST_LIBS += ['unit_test_framework']
        conf.define('HAVE_TESTS', 1)

    conf.check_boost(lib=USED_BOOST_LIBS, mandatory=True, mt=True)
    if conf.env.BOOST_VERSION_NUMBER < 105800:
        conf.fatal('Minimum required Boost version is 1.58.0\n'
                   'Please upgrade your distribution or manually install a newer version of Boost'
                   ' (https://redmine.named-data.net/projects/nfd/wiki/Boost_FAQ)')

    if not conf.options.with_sqlite_locking:
        conf.define('DISABLE_SQLITE3_FS_LOCKING', 1)

    if conf.env['HAVE_OSX_FRAMEWORKS']:
        conf.env['WITH_OSX_KEYCHAIN'] = conf.options.with_osx_keychain
        if conf.options.with_osx_keychain:
            conf.define('WITH_OSX_KEYCHAIN', 1)
    else:
        conf.env['WITH_OSX_KEYCHAIN'] = False

    conf.check_compiler_flags()

    # Loading "late" to prevent tests from being compiled with profiling flags
    conf.load('coverage')

    conf.load('sanitizers')

    conf.define('SYSCONFDIR', conf.env['SYSCONFDIR'])

    if not conf.env.enable_static:
        # If there happens to be a static library, waf will put the corresponding -L flags
        # before dynamic library flags.  This can result in compilation failure when the
        # system has a different version of the ndn-cxx library installed.
        conf.env['STLIBPATH'] = ['.'] + conf.env['STLIBPATH']

    # config file will contain all defines that were added using conf.define('xxx'...)
    # Everything that was added directly to conf.env['DEFINES'] will not appear in the
    # config file and will be added using compiler directives in the command line.
    conf.write_config_header('ndn-cxx/ndn-cxx-config.hpp', define_prefix='NDN_CXX_')

def build(bld):
    version(bld)

    bld(features='subst',
        name='version.hpp',
        source='ndn-cxx/version.hpp.in',
        target='ndn-cxx/version.hpp',
        install_path=None,
        VERSION_STRING=VERSION_BASE,
        VERSION_BUILD=VERSION,
        VERSION=int(VERSION_SPLIT[0]) * 1000000 +
                int(VERSION_SPLIT[1]) * 1000 +
                int(VERSION_SPLIT[2]),
        VERSION_MAJOR=VERSION_SPLIT[0],
        VERSION_MINOR=VERSION_SPLIT[1],
        VERSION_PATCH=VERSION_SPLIT[2])

    if bld.env['HAVE_OSX_FRAMEWORKS']:
        # Need to disable precompiled headers for Objective-C++ code
        bld(features=['cxx'],
            target='ndn-cxx-mm-objects',
            source=bld.path.ant_glob('ndn-cxx/**/*-osx.mm'),
            use='BOOST PTHREAD OSX_COREFOUNDATION OSX_SECURITY OSX_SYSTEMCONFIGURATION OSX_FOUNDATION OSX_COREWLAN',
            includes='. ndn-cxx')

    libndn_cxx = dict(
        target='ndn-cxx',
        source=bld.path.ant_glob('ndn-cxx/**/*.cpp',
                                 excl=['ndn-cxx/**/*-osx.cpp',
                                       'ndn-cxx/**/*netlink*.cpp',
                                       'ndn-cxx/**/*-sqlite3.cpp']),
        features='pch',
        headers='ndn-cxx/common-pch.hpp',
        use='ndn-cxx-mm-objects version BOOST OPENSSL SQLITE3 RT PTHREAD',
        includes='. ndn-cxx',
        export_includes='. ndn-cxx',
        install_path='${LIBDIR}')

    if bld.env['HAVE_OSX_FRAMEWORKS']:
        libndn_cxx['source'] += bld.path.ant_glob('ndn-cxx/**/*-osx.cpp')
        libndn_cxx['use'] += ' OSX_COREFOUNDATION OSX_SECURITY OSX_SYSTEMCONFIGURATION OSX_FOUNDATION OSX_COREWLAN'

    if bld.env['HAVE_NETLINK']:
        libndn_cxx['source'] += bld.path.ant_glob('ndn-cxx/**/*netlink*.cpp')

    # In case we want to make it optional later
    libndn_cxx['source'] += bld.path.ant_glob('ndn-cxx/**/*-sqlite3.cpp')

    if bld.env.enable_shared:
        bld.shlib(name='ndn-cxx',
                  vnum=VERSION_BASE,
                  cnum=VERSION_BASE,
                  **libndn_cxx)

    if bld.env.enable_static:
        bld.stlib(name='ndn-cxx-static' if bld.env.enable_shared else 'ndn-cxx',
                  **libndn_cxx)

    # Prepare flags that should go to pkgconfig file
    pkgconfig_libs = []
    pkgconfig_ldflags = []
    pkgconfig_linkflags = []
    pkgconfig_includes = []
    pkgconfig_cxxflags = []
    for lib in Utils.to_list(libndn_cxx['use']):
        if bld.env['LIB_%s' % lib]:
            pkgconfig_libs += Utils.to_list(bld.env['LIB_%s' % lib])
        if bld.env['LIBPATH_%s' % lib]:
            pkgconfig_ldflags += Utils.to_list(bld.env['LIBPATH_%s' % lib])
        if bld.env['INCLUDES_%s' % lib]:
            pkgconfig_includes += Utils.to_list(bld.env['INCLUDES_%s' % lib])
        if bld.env['LINKFLAGS_%s' % lib]:
            pkgconfig_linkflags += Utils.to_list(bld.env['LINKFLAGS_%s' % lib])
        if bld.env['CXXFLAGS_%s' % lib]:
            pkgconfig_cxxflags += Utils.to_list(bld.env['CXXFLAGS_%s' % lib])

    EXTRA_FRAMEWORKS = ''
    if bld.env['HAVE_OSX_FRAMEWORKS']:
        EXTRA_FRAMEWORKS = '-framework CoreFoundation -framework Security -framework SystemConfiguration -framework Foundation -framework CoreWLAN'

    def uniq(alist):
        seen = set()
        return [x for x in alist if x not in seen and not seen.add(x)]

    pkconfig = bld(features='subst',
         source='libndn-cxx.pc.in',
         target='libndn-cxx.pc',
         install_path='${LIBDIR}/pkgconfig',
         VERSION=VERSION_BASE,

         # This probably not the right thing to do, but to simplify life of apps
         # that use the library
         EXTRA_LIBS=' '.join([('-l%s' % i) for i in uniq(pkgconfig_libs)]),
         EXTRA_LDFLAGS=' '.join([('-L%s' % i) for i in uniq(pkgconfig_ldflags)]),
         EXTRA_LINKFLAGS=' '.join(uniq(pkgconfig_linkflags)),
         EXTRA_INCLUDES=' '.join([('-I%s' % i) for i in uniq(pkgconfig_includes)]),
         EXTRA_CXXFLAGS=' '.join(uniq(pkgconfig_cxxflags)),
         EXTRA_FRAMEWORKS=EXTRA_FRAMEWORKS)

    if bld.env['WITH_TESTS']:
        bld.recurse('tests')

    if bld.env['WITH_TOOLS']:
        bld.recurse('tools')

    if bld.env['WITH_EXAMPLES']:
        bld.recurse('examples')

    headers = bld.path.ant_glob('ndn-cxx/**/*.hpp',
                                excl=['ndn-cxx/**/*-osx.hpp',
                                      'ndn-cxx/**/*netlink*.hpp',
                                      'ndn-cxx/**/*-sqlite3.hpp',
                                      'ndn-cxx/**/detail/**/*'])

    if bld.env['HAVE_OSX_FRAMEWORKS']:
        headers += bld.path.ant_glob('ndn-cxx/**/*-osx.hpp', excl='ndn-cxx/**/detail/**/*')

    if bld.env['HAVE_NETLINK']:
        headers += bld.path.ant_glob('ndn-cxx/**/*netlink*.hpp', excl='ndn-cxx/**/detail/**/*')

    # In case we want to make it optional later
    headers += bld.path.ant_glob('ndn-cxx/**/*-sqlite3.hpp', excl='ndn-cxx/**/detail/**/*')

    bld.install_files(bld.env['INCLUDEDIR'], headers, relative_trick=True)

    bld.install_files('%s/ndn-cxx' % bld.env['INCLUDEDIR'],
                      bld.path.find_resource('ndn-cxx/ndn-cxx-config.hpp'))

    bld.install_files('%s/ndn-cxx' % bld.env['INCLUDEDIR'],
                      bld.path.find_resource('ndn-cxx/version.hpp'))

    bld.install_files('${SYSCONFDIR}/ndn', 'client.conf.sample')

    if bld.env.SPHINX_BUILD:
        bld(features='sphinx',
            name='manpages',
            builder='man',
            config='docs/conf.py',
            outdir='docs/manpages',
            source=bld.path.ant_glob('docs/manpages/**/*.rst'),
            install_path='${MANDIR}',
            VERSION=VERSION)

def docs(bld):
    from waflib import Options
    Options.commands = ['doxygen', 'sphinx'] + Options.commands

def doxygen(bld):
    version(bld)

    if not bld.env.DOXYGEN:
        bld.fatal('Cannot build documentation ("doxygen" not found in PATH)')

    bld(features='subst',
        name='doxygen.conf',
        source=['docs/doxygen.conf.in',
                'docs/named_data_theme/named_data_footer-with-analytics.html.in'],
        target=['docs/doxygen.conf',
                'docs/named_data_theme/named_data_footer-with-analytics.html'],
        VERSION=VERSION,
        HTML_FOOTER='../build/docs/named_data_theme/named_data_footer-with-analytics.html' \
                        if os.getenv('GOOGLE_ANALYTICS', None) \
                        else '../docs/named_data_theme/named_data_footer.html',
        GOOGLE_ANALYTICS=os.getenv('GOOGLE_ANALYTICS', ''))

    bld(features='doxygen',
        doxyfile='docs/doxygen.conf',
        use='doxygen.conf')

def sphinx(bld):
    version(bld)

    if not bld.env.SPHINX_BUILD:
        bld.fatal('Cannot build documentation ("sphinx-build" not found in PATH)')

    bld(features='sphinx',
        config='docs/conf.py',
        outdir='docs',
        source=bld.path.ant_glob('docs/**/*.rst'),
        VERSION=VERSION)

def version(ctx):
    # don't execute more than once
    if getattr(Context.g_module, 'VERSION_BASE', None):
        return

    Context.g_module.VERSION_BASE = Context.g_module.VERSION
    Context.g_module.VERSION_SPLIT = VERSION_BASE.split('.')

    # first, try to get a version string from git
    gotVersionFromGit = False
    try:
        cmd = ['git', 'describe', '--always', '--match', '%s*' % GIT_TAG_PREFIX]
        out = subprocess.check_output(cmd, universal_newlines=True).strip()
        if out:
            gotVersionFromGit = True
            if out.startswith(GIT_TAG_PREFIX):
                Context.g_module.VERSION = out.lstrip(GIT_TAG_PREFIX)
            else:
                # no tags matched
                Context.g_module.VERSION = '%s-commit-%s' % (VERSION_BASE, out)
    except (OSError, subprocess.CalledProcessError):
        pass

    versionFile = ctx.path.find_node('VERSION')
    if not gotVersionFromGit and versionFile is not None:
        try:
            Context.g_module.VERSION = versionFile.read()
            return
        except EnvironmentError:
            pass

    # version was obtained from git, update VERSION file if necessary
    if versionFile is not None:
        try:
            if versionFile.read() == Context.g_module.VERSION:
                # already up-to-date
                return
        except EnvironmentError as e:
            Logs.warn('%s exists but is not readable (%s)' % (versionFile, e.strerror))
    else:
        versionFile = ctx.path.make_node('VERSION')

    try:
        versionFile.write(Context.g_module.VERSION)
    except EnvironmentError as e:
        Logs.warn('%s is not writable (%s)' % (versionFile, e.strerror))

def dist(ctx):
    version(ctx)

def distcheck(ctx):
    version(ctx)
