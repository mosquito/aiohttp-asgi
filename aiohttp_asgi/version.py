author_info = (("Dmitry Orlov", "me@mosquito.su"),)

package_info = "Adapter to running ASGI applications on aiohttp"
package_license = "Apache Software License"

team_email = "me@mosquito.su"

version_info = (0, 4, 0)

__author__ = ", ".join("{} <{}>".format(*info) for info in author_info)
__version__ = ".".join(map(str, version_info))
