import discord
from discord.ui import Select


class UpdateSelector(Select):
    def __init__(self, search_results, information):
        self.search_results = search_results
        self.information = information
        max_options = 10
        options = [
            discord.SelectOption(
                label=f"{user['paymentPerson']} | {user['server']} ({user['status']})",
                value=str(idx),
                description=f"Discord: {user['primaryDiscord'] if user['primaryDiscord'] else 'N/A'} | Email: {user['primaryEmail']}",
                emoji="👤"
            )
            for idx, user in enumerate(search_results[:max_options])
        ]
        max_values = min(len(search_results), max_options)
        super().__init__(placeholder="Please select the user", options=options, min_values=1, max_values=max_values)

    async def callback(self, interaction: discord.Interaction):
        selected_user_indices = [int(value) for value in self.values]
        selected_users = [self.search_results[idx] for idx in selected_user_indices]
        self.information.setdefault('users', []).extend(selected_users)

        if self.information['what'] == 'payment':
            await self.view.handle_payment(interaction, selected_users)
        elif self.information['what'] == 'move':
            await self.view.handle_move(interaction, selected_users)