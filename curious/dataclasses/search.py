"""
Wrappers for Search objects.

.. currentmodule:: curious.dataclasses.search
"""
import collections
import functools
import typing
import weakref

from curious.dataclasses import channel as dt_channel, guild as dt_guild, member as dt_member, \
    message as dt_message, user as dt_user


class MessageGroup:
    """
    A small class that returns messages from a message group.
    """

    __slots__ = "msgs",

    def __init__(self, msgs: 'typing.List[dt_message.Message]'):
        self.msgs = msgs

    # generic magic methods
    def __getitem__(self, item):
        return self.msgs[item]

    def __iter__(self):
        return iter(self.msgs)

    def __repr__(self):
        return "<MessageGroup msgs='{}'>".format(self.msgs)

    @property
    def before(self) -> 'typing.Tuple[dt_message.Message, dt_message.Message]':
        """
        :return: The two :class:`~.Message` objects that happen before the requested message.
        """
        return self.msgs[0], self.msgs[1]

    @property
    def message(self) -> 'dt_message.Message':
        """
        :return: The :class:`~.Message` that matched this search query. 
        """
        return self.msgs[2]

    @property
    def after(self) -> 'typing.Tuple[dt_message.Message, dt_message.Message]':
        """
        :return: The two :class:`~.Message` objects that happen after the requested message. 
        """
        return self.msgs[3], self.msgs[4]


class SearchResults(collections.AsyncIterator):
    """
    An async iterator that can be used to iterate over the results of a search.
    This will automatically fill results, and return messages as appropriate.
    
    The return type of iterating over this is a :class:`~.MessageGroup`, which contains the messages 
    around the message that matched the search result.
    
    .. code-block:: python
    
        async for i in sr:
            print(i.before)  # 2 messages from before
            print(i.message) # the message that matched
            print(i.after)   # 2 messages from after
            
    """
    def __init__(self, sq: 'SearchQuery'):
        self.sq = sq

        # state vars
        self.page = 0
        self.groups = collections.deque()

        self._limit = -1
        self._total_count = 0

    def __repr__(self):
        return "<SearchResults page='{}' messages='{}'>".format(self.page, len(self.groups))

    # builder methods
    def limit(self, limit: int=-1) -> 'SearchResults':
        """
        Sets the maximum messages to fetch from this search result.
        
        .. code-block:: python
        
            async for group in sr.limit(25):
                ...
        
        :param limit: The limit to set.
        :return: This :class:`~.SearchResults`.
        """
        self._limit = limit
        return self

    async def fetch_next_page(self):
        """
        Fetches the next page of results from the SearchQuery.
        """
        if self._limit != -1 and self._total_count >= self._limit:
            return

        results = await self.sq.execute(page=self.page)

        # add a new messagegroup to the end
        for r in results:
            self.groups.append(MessageGroup(r))

        self.page += 1

    def get_next(self) -> 'MessageGroup':
        """
        Gets the next page of results.
        
        If no results were found, this will raise an IndexError, and you must fetch the next page 
        with :meth:`.SearchResults.fetch_next_page`.
        
        :return: A :class:`~.MessageGroup` for the next page of results, if applicable.
        """
        # prevent more fetching
        if self._limit != -1 and self._total_count >= self._limit:
            raise IndexError

        popped = self.groups.popleft()
        self._total_count += len(popped.msgs)
        return popped

    async def __anext__(self) -> 'MessageGroup':
        try:
            return self.get_next()
        except IndexError:
            await self.fetch_next_page()
            # try and pop left again
            # if it fails no messages were returned
            try:
                return self.get_next()
            except IndexError:
                raise StopAsyncIteration


class SearchQuery(object):
    """
    Represents a search query to be sent to Discord. This is a simple wrapper over the HTTP API.
    
    For example, to search a channel called ``general`` for messages with the content ``heck``:
    
    .. code-block:: python3

        with ctx.guild.search as sq:
            sq.content = "heck"
            sq.channel = next(filter(lambda c: c.name == "general", ctx.guild.channels), None)
             
        async for result in sq.results:
            ...  # do whatever with the messages returned.
            
    You can get results out of the query in two ways:
    
    .. code-block:: python3
    
        sq = SearchQuery(ctx.guild)
        sq.content = "heck"
        
        # form 1
        async for item in sq.results:
            ...
            
        # form 2
        results = await sq.get_messages()
        for result in results:
            ...
            
    It is recommended to use the ``async for`` form, as this will automatically page the results 
    and return the next page of results as soon as the current one is exhausted.
    """

    def __init__(self, guild: 'dt_guild.Guild' = None, channel: 'dt_channel.Channel' = None):
        """
        :param guild: The :class:`~.Guild` to search the messages for.
        :param channel: The :class:`~.Channel` to search messages for. Only used for DMs.
        """
        self._guild = weakref.ref(guild) if guild is not None else None

        # internal vars used for the search
        self._channel = weakref.ref(channel) if channel is not None else None
        self._query = None  # type: str
        self._author = None  # type: typing.Union[dt_user.User, dt_member.Member]

    def make_params(self) -> typing.Dict[str, str]:
        """
        :return: The dict of parameters to send for this request. 
        """
        params = {}

        if self.guild is not None and self.channel is not None:
            params["channel_id"] = self.channel.id

        if self._query is not None:
            params["content"] = self._query

        if self._author is not None:
            params["author_id"] = self._author.id

        # TODO: Datetimes and `has:`

        return params

    # magic methods
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def __repr__(self):
        return "<SearchQuery guild='{}' channel='{}'>".format(self.guild, self.channel)

    # internal properties
    @property
    def _http_meth(self):
        """
        :return: The built URL to execute this search query on. 
        """
        if self.guild is not None:
            return functools.partial(self._bot.http.search_guild, self.guild.id)

        return functools.partial(self._bot.http.search_channel, self.channel.id)

    @property
    def _bot(self):
        if self._guild is not None:
            return self._guild()._bot

        return self._channel()._bot

    # public properties
    @property
    def guild(self) -> 'typing.Union[dt_guild.Guild, None]':
        """
        :return: The :class:`~.Guild` this search query is searching. 
        """
        if self._guild is None:
            return None

        return self._guild()

    @property
    def channel(self) -> 'typing.Union[dt_channel.Channel, None]':
        """
        The :class:`~.Channel` that is being searched.
        
        .. note::
            
            If this a DM, this will not be added in the params.
        
        :getter: Gets the :class:`~.Channel` to be searched.
        :setter: Sets the :class:`~.Channel` to be searched. 
        """
        if self._channel is None:
            return None

        return self._channel()

    @channel.setter
    def channel(self, value):
        if not isinstance(value, dt_channel.Channel):
            raise TypeError("Must provide a Channel object")

        if value.type is dt_channel.ChannelType.VOICE:
            raise ValueError("Cannot search a voice channel")

        if self._guild is not None and value.guild is None:
            raise ValueError("Channel must not be a private channel for searching a guild")

        if self._guild is not None and value.guild != self._guild:
            raise ValueError("Channel to search must be in the same guild")

        self._channel = weakref.ref(value)

    @property
    def content(self) -> str:
        """
        The str content that is being searched.
        
        :getter: Gets the ``str`` content to be searched.
        :setter: Sets the ``str`` content to be searched.
        """
        return self._query

    @content.setter
    def content(self, value):
        self._query = value

    @property
    def results(self) -> 'SearchResults':
        """
        A simple way of accessing the search results for a search query.
        
        :return: A :class:`~.SearchResults` representing the results of this query. 
        """
        return SearchResults(self)

    # workhouse methods
    async def execute(self, page: int = 0) -> 'typing.List[typing.List[dt_message.Message]]':
        """
        Executes the search query.
        
        .. warning::
            
            This is an internal method, used by the library. Use :meth:`.get_messages` instead
            of this.
        
        :param page: The page of results to return.
        :return: A list of :class:`~.Message` which returns the results of the search query.
        """
        func = self._http_meth
        params = self.make_params()

        # get the offset page
        params["offset"] = page * 25
        # make the http request
        res = await func(params)

        message_blocks = []

        # parse all of the message objects
        for group in res.get("messages", []):
            message_blocks.append([self._bot.state.make_message(m) for m in group])

        return message_blocks

    async def get_messages(self, page: int = 0) -> 'SearchResults':
        """
        Executes the search query and gets the messages for the specified page.
        
        :param page: The page of results to return. 
        :return: A :class:`~.SearchResult` that can be used to search the results.
        """
        res = SearchResults(self)
        res.page = page
        await res.fetch_next_page()
        return res
