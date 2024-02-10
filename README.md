<div align="center">

# managarr

A Discord bot to add/update users on plex and discord with subscription updates like: became paying member, updates to subscription model, and payment updates.

[![Release](https://img.shields.io/github/v/release/mtrogman/managarr?color=yellow&include_prereleases&label=version&style=flat-square)](https://github.com/mtrogman/managarr/releases)
[![Docker](https://img.shields.io/docker/pulls/mtrogman/managarr?style=flat-square)](https://hub.docker.com/r/mtrogman/managarr)
[![Licence](https://img.shields.io/github/license/mtrogman/managarr?style=flat-square)](https://opensource.org/licenses/GPL-3.0)


<img src="https://raw.githubusercontent.com/mtrogman/managarr/master/logo.png" alt="logo">

</div>

# Features

managarr uses discord in conjunction with MariaDB, Plex, and Discord to manage users subscriptions.

# Commands

/payment_recieved [User] [Amount]
    This cmd will use [User] and search for it in primaryDiscord, paymentPerson, primaryEmail and return all matches.  Once you select the user(s) it will calculate the amount based off the values in the config and [Amount].  It will calculate the new end date for the user and also increment the paidAmount of the user to match the amount recieved.  If the payment amount matches one of the dicount points (3/6/12 Months) it calculates the paid months by that number, if it doesnt match one of those values it defaults to 1 month and calculates payment off that price and extends users subscription by the amount of months that the payment covers.  If the payment doesnt cleanly add up the extra amount is also added to the users payment.

# Installation and setup

## Requirements

- Plex
- MariaDB
- A Discord server
- Docker
- [A Discord bot token](https://www.digitaltrends.com/gaming/how-to-make-a-discord-bot/)
    - Permissions required:
        - Manage Channels
        - View Channels
        - Send Messages
        - Manage Messages
        - Read Message History
        - Add Reactions
        - Manage Emojis


managarr runs as a Docker container. The Dockerfile is included in this repository, or can be pulled
from [Docker Hub](https://hub.docker.com/r/mtrogman/managarr)
or [GitHub Packages](https://github.com/mtrogman/remanagarr/pkgs/container/managarr).

### Volumes

You will need to map the following volumes:

| Host Path              | Container Path | Reason                                                                                            |
|------------------------|----------------|---------------------------------------------------------------------------------------------------|
| /path/to/config/folder | /config        | Required, path to the folder containing the configuration file                                    |



You can also set these variables via a configuration file:

1. Map the `/config` directory (see volumes above)
2. Enter the mapped directory on your host machine
3. Rename the ``config.yml.example`` file in the path to ``config.yml``
4. Complete the variables in ``config.yml``

# Development

This bot is still a work in progress. If you have any ideas for improving or adding to managarr, please open an issue
or a pull request.

# Contact

Please leave a pull request if you would like to contribute.

Feel free to check out my other projects here on [GitHub](https://github.com/mtrogman) or join my Discord server below.

<div align="center">
	<p>
		<a href="https://discord.gg/jp68q5C3pr"><img src="https://discordapp.com/api/guilds/783077604101455882/widget.png?style=banner2" alt="" /></a>
	</p>
</div>

## Contributors ✨

Thanks goes to these wonderful people:

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->

### Contributors

<table>
<tr>
    <td align="center" style="word-wrap: break-word; width: 75.0; height: 75.0">
        <a href=https://github.com/mtrogman>
            <img src=https://avatars.githubusercontent.com/u/47980633?v=4 width="50;"  style="border-radius:50%;align-items:center;justify-content:center;overflow:hidden;padding-top:10px" alt=trog/>
            <br />
            <sub style="font-size:14px"><b>trog</b></sub>
        </a>
    </td>
</tr>
</table>

<table>

</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->
