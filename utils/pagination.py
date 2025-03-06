"""
Pagination utilities for API responses
"""
from typing import List, Dict, Any, TypeVar, Generic, Optional, Union, Tuple
from math import ceil

from fastapi import Query
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel
from tortoise.queryset import QuerySet
from tortoise.contrib.pydantic import pydantic_queryset_creator


# Type variable for generic type hints
T = TypeVar('T')


class PageParams(BaseModel):
    """
    Pagination parameters for API requests
    """
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")
    # Optional parameters for advanced pagination
    cursor: Optional[str] = Field(None, description="Cursor for cursor-based pagination")
    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: Optional[str] = Field(None, description="Sort order (asc or desc)")
    
    def get_offset(self) -> int:
        """
        Get the offset for SQL LIMIT/OFFSET pagination
        
        Returns:
            Offset value
        """
        return (self.page - 1) * self.page_size
    
    def get_limit(self) -> int:
        """
        Get the limit for SQL LIMIT/OFFSET pagination
        
        Returns:
            Limit value
        """
        return self.page_size


class PageInfo(BaseModel):
    """
    Pagination information for API responses
    """
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    total_items: int = Field(..., description="Total number of items")
    has_previous: bool = Field(..., description="Whether there is a previous page")
    has_next: bool = Field(..., description="Whether there is a next page")
    # Optional fields for cursor-based pagination
    next_cursor: Optional[str] = Field(None, description="Cursor for next page")
    previous_cursor: Optional[str] = Field(None, description="Cursor for previous page")
    
    @classmethod
    def create(
        cls,
        page: int,
        page_size: int,
        total_items: int,
        next_cursor: Optional[str] = None,
        previous_cursor: Optional[str] = None
    ) -> 'PageInfo':
        """
        Create PageInfo from pagination parameters
        
        Args:
            page: Current page number
            page_size: Items per page
            total_items: Total number of items
            next_cursor: Cursor for next page
            previous_cursor: Cursor for previous page
            
        Returns:
            PageInfo instance
        """
        total_pages = ceil(total_items / page_size) if total_items > 0 else 1
        
        return cls(
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            total_items=total_items,
            has_previous=page > 1,
            has_next=page < total_pages,
            next_cursor=next_cursor,
            previous_cursor=previous_cursor
        )


class Page(GenericModel, Generic[T]):
    """
    Paginated API response with items and pagination info
    """
    items: List[T] = Field(..., description="Page items")
    page_info: PageInfo = Field(..., description="Pagination information")
    
    @classmethod
    def create(
        cls,
        items: List[T],
        page_params: PageParams,
        total_items: int,
        next_cursor: Optional[str] = None,
        previous_cursor: Optional[str] = None
    ) -> 'Page[T]':
        """
        Create Page from items and pagination parameters
        
        Args:
            items: Page items
            page_params: Pagination parameters
            total_items: Total number of items
            next_cursor: Cursor for next page
            previous_cursor: Cursor for previous page
            
        Returns:
            Page instance
        """
        page_info = PageInfo.create(
            page=page_params.page,
            page_size=page_params.page_size,
            total_items=total_items,
            next_cursor=next_cursor,
            previous_cursor=previous_cursor
        )
        
        return cls(items=items, page_info=page_info)


async def paginate_queryset(
    queryset: QuerySet,
    page_params: PageParams,
    pydantic_model: Any,
    prefetch_related: Optional[List[str]] = None
) -> Page:
    """
    Paginate a Tortoise ORM queryset
    
    Args:
        queryset: Tortoise ORM queryset
        page_params: Pagination parameters
        pydantic_model: Pydantic model for serialization
        prefetch_related: List of relations to prefetch
        
    Returns:
        Paginated response
    """
    # Apply sorting if specified
    if page_params.sort_by:
        sort_prefix = "-" if page_params.sort_order == "desc" else ""
        queryset = queryset.order_by(f"{sort_prefix}{page_params.sort_by}")
    
    # Get total count for pagination info
    total_items = await queryset.count()
    
    # Apply pagination
    queryset = queryset.offset(page_params.get_offset()).limit(page_params.get_limit())
    
    # Prefetch related entities if specified
    if prefetch_related:
        queryset = queryset.prefetch_related(*prefetch_related)
    
    # Convert queryset to Pydantic models
    pydantic_queryset = pydantic_queryset_creator(queryset.model)
    results = await pydantic_queryset.from_queryset(queryset)
    
    # Create paginated response
    return Page.create(
        items=results,
        page_params=page_params,
        total_items=total_items
    )


async def paginate_results(
    items: List[Any],
    page_params: PageParams,
    total_items: Optional[int] = None
) -> Page:
    """
    Paginate a list of items
    
    Args:
        items: List of items
        page_params: Pagination parameters
        total_items: Total number of items (if known)
        
    Returns:
        Paginated response
    """
    # Calculate total items if not provided
    if total_items is None:
        total_items = len(items)
    
    # Create paginated response
    return Page.create(
        items=items,
        page_params=page_params,
        total_items=total_items
    )


def get_page_params(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    cursor: Optional[str] = Query(None, description="Cursor for cursor-based pagination"),
    sort_by: Optional[str] = Query(None, description="Field to sort by"),
    sort_order: Optional[str] = Query(None, description="Sort order (asc or desc)")
) -> PageParams:
    """
    Get pagination parameters from query parameters
    
    Use this as a FastAPI dependency for endpoints that need pagination
    
    Args:
        page: Page number
        page_size: Items per page
        cursor: Cursor for cursor-based pagination
        sort_by: Field to sort by
        sort_order: Sort order (asc or desc)
        
    Returns:
        PageParams instance
    """
    return PageParams(
        page=page,
        page_size=page_size,
        cursor=cursor,
        sort_by=sort_by,
        sort_order=sort_order
    )