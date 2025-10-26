from typing import Literal, get_args

PostTag = Literal['discussion', 'question', 'tutorial', 'resource', 'experience']
FeedSort = Literal['latest', 'trending']
FeedCriteria = Literal[*(get_args(FeedSort) + get_args(PostTag))]
FileChange = Literal['add', 'remove', 'move']