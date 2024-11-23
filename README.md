<div align="center">

# managarr

Managarr is a Discord bot designed to streamline the management of Plex subscriptions. It automates tasks such as adding new users, handling payments, moving users between Plex servers, and managing subscription notifications. Built with Python and leveraging the Discord API, Managarr aims to save time and reduce manual intervention.

[![Release](https://img.shields.io/github/v/release/mtrogman/managarr?color=yellow&include_prereleases&label=version&style=flat-square)](https://github.com/mtrogman/managarr/releases)
[![Docker](https://img.shields.io/docker/pulls/mtrogman/managarr?style=flat-square)](https://hub.docker.com/r/mtrogman/managarr)
[![Licence](https://img.shields.io/github/license/mtrogman/managarr?style=flat-square)](https://opensource.org/licenses/GPL-3.0)


<img src="https://raw.githubusercontent.com/mtrogman/managarr/master/logo.png" alt="logo">

</div>

# Features

- Add New Users: Quickly add new Plex users via Discord with minimal manual steps.
- Payments: Track and update subscriptions when payments are received, extending user access automatically.
- Move Users: Seamlessly transfer users between Plex instances while keeping their subscriptions intact.
- Multiple Medium Notifications: Users are notified through Discord and email for critical updates.

# Commands

/payment_received [User] [Amount]
Handles subscription payments for a user:

- Searches for the specified [User] in fields such as primaryDiscord, paymentPerson, and primaryEmail, returning all matches.
- After selecting the user(s), calculates the subscription extension based on the [Amount] paid:
    - Uses values from the configuration (e.g., pricing for 1, 3, 6, or 12 months).
    - If the payment amount matches a discount point, it applies the corresponding duration (e.g., 3 months for a 3-month payment).
    - For payments that don’t cleanly match, the bot defaults to 1 month and carries over any extra amount as credit.
- Updates the user’s paidAmount and extends their subscription end date.

/add_new_user [User]
Adds a new user to the system:

- Searches for the specified [User] in Discord and retrieves relevant user details.
- Prompts for confirmation before adding the user to the database.
- Automatically assigns them the correct Discord role and updates their status.

/move_user [User] [New_Server]
Transfers a user to a different Plex server:

- Updates the user’s subscription to reflect the libraries on the new Plex server.
- Ensures their subscription details, such as end date and access permissions, remain intact.
- Notifies the user of the change via Discord and email.


/add_plex_server [Server_Name]
Adds a new Plex server to the system configuration:

- Registers the new server with its name, token, and associated libraries.
- Updates the bot configuration to recognize the new server for user management and subscriptions.
- Useful for scaling and managing multiple Plex instances

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
